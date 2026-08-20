import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/auth_interceptor.dart';
import 'package:nexora_mobile/core/network/token_refresher.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// In-memory secure storage. `flutter_secure_storage` needs platform channels,
/// which do not exist under `flutter test`.
class _MemoryStorage implements FlutterSecureStorage {
  final Map<String, String> values = {};

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      values[key];

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      values.remove(key);

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not needed in tests');
}

/// Scriptable transport that records every request it sees.
class _ScriptedAdapter implements HttpClientAdapter {
  _ScriptedAdapter(this.handler);

  final ResponseBody Function(RequestOptions options) handler;
  final List<RequestOptions> requests = [];

  int countFor(String path) => requests.where((r) => r.path == path).length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(int status, Map<String, dynamic> body) =>
    ResponseBody.fromBytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

SecureStorageService _storageWith({String? refresh, String? device}) {
  final backing = _MemoryStorage();
  if (refresh != null) {
    backing.values['nexora.auth.refresh_token'] = refresh;
  }
  if (device != null) {
    backing.values['nexora.device.id'] = device;
  }
  backing.values['nexora.auth.token'] = 'expired-access-token';
  return SecureStorageService(backing);
}

void main() {
  group('TokenRefresher', () {
    test('stores the new access token and the rotated refresh token', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      dio.httpClientAdapter = _ScriptedAdapter(
        (_) => _json(200, {
          'token': 'access-new',
          'refresh_token': 'refresh-new',
        }),
      );

      final outcome = await TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
        httpClient: dio,
      ).refresh();

      expect(outcome, RefreshOutcome.refreshed);
      expect(await storage.readToken(), 'access-new');
      // The old token is dead server-side; keeping it would strand the session.
      expect(await storage.readRefreshToken(), 'refresh-new');
    });

    test('reports unavailable when there is no refresh token', () async {
      final storage = _storageWith(device: 'device-1');
      final outcome = await TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
      ).refresh();
      expect(outcome, RefreshOutcome.unavailable);
    });

    test('a 401 rejects the session and clears the refresh token', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      dio.httpClientAdapter = _ScriptedAdapter(
        (_) => _json(401, {'detail': 'Refresh token already used'}),
      );

      final outcome = await TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
        httpClient: dio,
      ).refresh();

      expect(outcome, RefreshOutcome.rejected);
      expect(await storage.readRefreshToken(), isNull);
    });

    test('a 500 is transient and does NOT discard the refresh token', () async {
      // Signing users out because the HO server hiccupped would be worse than
      // the expired token they started with.
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      dio.httpClientAdapter = _ScriptedAdapter(
        (_) => _json(500, {'detail': 'boom'}),
      );

      final outcome = await TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
        httpClient: dio,
      ).refresh();

      expect(outcome, RefreshOutcome.transient);
      expect(await storage.readRefreshToken(), 'refresh-old');
    });

    test('concurrent callers share ONE refresh request', () async {
      // Critical: refresh tokens are single-use and the server treats a replay
      // as theft by revoking the whole device chain. Two parallel refreshes
      // would therefore sign the user out.
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      final adapter = _ScriptedAdapter(
        (_) => _json(200, {
          'token': 'access-new',
          'refresh_token': 'refresh-new',
        }),
      );
      dio.httpClientAdapter = adapter;

      final refresher = TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
        httpClient: dio,
      );

      final results = await Future.wait([
        refresher.refresh(),
        refresher.refresh(),
        refresher.refresh(),
      ]);

      expect(results, everyElement(RefreshOutcome.refreshed));
      expect(adapter.countFor(ApiEndpoints.mobileRefresh), 1);
    });

    test('a later refresh starts a fresh request', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      final adapter = _ScriptedAdapter(
        (_) => _json(200, {'token': 'a', 'refresh_token': 'b'}),
      );
      dio.httpClientAdapter = adapter;

      final refresher = TokenRefresher(
        storage: storage,
        baseUrl: 'http://backend.test',
        httpClient: dio,
      );

      await refresher.refresh();
      await refresher.refresh();

      expect(adapter.countFor(ApiEndpoints.mobileRefresh), 2);
    });
  });

  group('AuthInterceptor', () {
    /// Builds a client whose protected endpoint 401s until the token changes.
    Dio buildAppDio({
      required SecureStorageService storage,
      required void Function() onUnauthorized,
      required _ScriptedAdapter adapter,
    }) {
      final dio = Dio(BaseOptions(baseUrl: 'http://backend.test'));
      dio.httpClientAdapter = adapter;
      dio.interceptors.add(
        AuthInterceptor(
          storage: storage,
          onUnauthorized: () async => onUnauthorized(),
          refresher: TokenRefresher(
            storage: storage,
            baseUrl: 'http://backend.test',
            httpClient: dio,
          ),
          retryClient: dio,
        ),
      );
      return dio;
    }

    test('refreshes then replays the original request on 401', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      var loggedOut = false;
      late _ScriptedAdapter adapter;

      adapter = _ScriptedAdapter((options) {
        if (options.path == ApiEndpoints.mobileRefresh) {
          return _json(200, {
            'token': 'access-new',
            'refresh_token': 'refresh-new',
          });
        }
        final auth = options.headers['Authorization'];
        if (auth == 'Bearer access-new') {
          return _json(200, {'ok': true});
        }
        return _json(401, {'detail': 'Token expired'});
      });

      final dio = buildAppDio(
        storage: storage,
        onUnauthorized: () => loggedOut = true,
        adapter: adapter,
      );

      final res = await dio.get<Map<String, dynamic>>('/api/protected');

      expect(res.statusCode, 200);
      expect(res.data?['ok'], true);
      expect(loggedOut, isFalse,
          reason: 'session must survive a refreshable 401');
      expect(adapter.countFor('/api/protected'), 2,
          reason: 'original + replay');
    });

    test('ends the session when the refresh token is rejected', () async {
      final storage = _storageWith(refresh: 'refresh-dead', device: 'device-1');
      var loggedOut = false;

      final adapter = _ScriptedAdapter((options) {
        if (options.path == ApiEndpoints.mobileRefresh) {
          return _json(401, {'detail': 'Refresh token already used'});
        }
        return _json(401, {'detail': 'Token expired'});
      });

      final dio = buildAppDio(
        storage: storage,
        onUnauthorized: () => loggedOut = true,
        adapter: adapter,
      );

      await expectLater(
        dio.get<Map<String, dynamic>>('/api/protected'),
        throwsA(isA<DioException>()),
      );
      expect(loggedOut, isTrue);
    });

    test('does not retry more than once', () async {
      // A server that 401s even with a fresh token must not loop forever.
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      var loggedOut = false;

      final adapter = _ScriptedAdapter((options) {
        if (options.path == ApiEndpoints.mobileRefresh) {
          return _json(200, {'token': 'new', 'refresh_token': 'newer'});
        }
        return _json(401, {'detail': 'Still unauthorized'});
      });

      final dio = buildAppDio(
        storage: storage,
        onUnauthorized: () => loggedOut = true,
        adapter: adapter,
      );

      await expectLater(
        dio.get<Map<String, dynamic>>('/api/protected'),
        throwsA(isA<DioException>()),
      );
      expect(adapter.countFor('/api/protected'), 2);
      expect(adapter.countFor(ApiEndpoints.mobileRefresh), 1);
      expect(loggedOut, isTrue);
    });

    test('keeps the session when refresh fails transiently', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      var loggedOut = false;

      final adapter = _ScriptedAdapter((options) {
        if (options.path == ApiEndpoints.mobileRefresh) {
          return _json(503, {'detail': 'server restarting'});
        }
        return _json(401, {'detail': 'Token expired'});
      });

      final dio = buildAppDio(
        storage: storage,
        onUnauthorized: () => loggedOut = true,
        adapter: adapter,
      );

      await expectLater(
        dio.get<Map<String, dynamic>>('/api/protected'),
        throwsA(isA<DioException>()),
      );
      expect(loggedOut, isFalse);
      expect(await storage.readRefreshToken(), 'refresh-old');
    });

    test('a public request that 401s never triggers a refresh', () async {
      final storage = _storageWith(refresh: 'refresh-old', device: 'device-1');
      var loggedOut = false;

      final adapter = _ScriptedAdapter(
        (_) => _json(401, {'detail': 'Invalid Username Or Password'}),
      );

      final dio = buildAppDio(
        storage: storage,
        onUnauthorized: () => loggedOut = true,
        adapter: adapter,
      );

      await expectLater(
        dio.post<Map<String, dynamic>>(
          ApiEndpoints.mobileLogin,
          data: const {},
          options: Options(extra: {'requiresAuth': false}),
        ),
        throwsA(isA<DioException>()),
      );

      expect(loggedOut, isFalse);
      expect(adapter.countFor(ApiEndpoints.mobileRefresh), 0);
    });
  });
}
