"""SFTP transport: for stores with internet access but no LAN/domain route to
HO and no shared filesystem, using SFTP (never plain FTP -- credentials and
package contents must stay encrypted in transit).

Requires the optional ``paramiko`` dependency. Import is deferred and guarded
so stores that never enable SFTP are unaffected if it is not installed.

Remote layout mirrors FileDropTransport::

    <remote_root>/inbox/<store_id>/<package>.zip
    <remote_root>/inbox/<store_id>/processed/<package>.zip
    <remote_root>/inbox/<store_id>/quarantine/<package>.zip
    <remote_root>/results/<store_id>/<result>.json
    <remote_root>/results/<store_id>/processed/<result>.json

Authentication is by private key (preferred) or password, both supplied via
environment variables referenced from config -- never hardcoded.
"""
import os
import posixpath
import tempfile

from store_agent.file_transfer.transport_base import SenderTransport


class SftpConfigError(RuntimeError):
    pass


def _connect(cfg):
    try:
        import paramiko
    except ImportError as ex:
        raise SftpConfigError(
            "SFTP transport requires the 'paramiko' package "
            "(pip install paramiko)"
        ) from ex

    host = cfg.get("host")
    port = int(cfg.get("port", 22))
    username = cfg.get("username")
    if not host or not username:
        raise SftpConfigError("SFTP transport config requires 'host' and 'username'")

    key_path = cfg.get("key_path")
    password_env = cfg.get("password_env")
    password = os.environ.get(password_env) if password_env else None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    known_hosts = cfg.get("known_hosts_path")
    if known_hosts and os.path.isfile(known_hosts):
        client.load_host_keys(known_hosts)

    if key_path:
        key_password_env = cfg.get("key_password_env")
        key_password = os.environ.get(key_password_env) if key_password_env else None
        client.connect(host, port=port, username=username, key_filename=key_path,
                       password=key_password, timeout=30)
    elif password:
        client.connect(host, port=port, username=username, password=password, timeout=30)
    else:
        raise SftpConfigError(
            "SFTP transport config requires 'key_path' or 'password_env'"
        )
    return client


def _ensure_dir(sftp, remote_dir):
    parts = remote_dir.strip("/").split("/")
    path = ""
    for part in parts:
        path = path + "/" + part
        try:
            sftp.stat(path)
        except IOError:
            sftp.mkdir(path)


class SftpSenderTransport(SenderTransport):
    def __init__(self, cfg, store_id):
        self.cfg = cfg
        self.store_id = str(store_id)
        self.remote_root = cfg.get("remote_root", "/nexora_sync").rstrip("/")
        self.inbox_dir = posixpath.join(self.remote_root, "inbox", self.store_id)
        self.results_dir = posixpath.join(self.remote_root, "results", self.store_id)
        self.results_processed_dir = posixpath.join(self.results_dir, "processed")

    def upload(self, local_path, remote_name):
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            _ensure_dir(sftp, self.inbox_dir)
            remote_tmp = posixpath.join(self.inbox_dir, remote_name + ".part")
            remote_final = posixpath.join(self.inbox_dir, remote_name)
            sftp.put(local_path, remote_tmp)
            sftp.rename(remote_tmp, remote_final)  # atomic on POSIX SFTP servers
        finally:
            client.close()

    def list_results(self):
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            try:
                entries = sftp.listdir(self.results_dir)
            except IOError:
                return []
            out = []
            for name in sorted(entries):
                if not name.endswith(".json"):
                    continue
                local_tmp = tempfile.NamedTemporaryFile(
                    prefix="nexora_result_", suffix=".json", delete=False
                )
                local_tmp.close()
                sftp.get(posixpath.join(self.results_dir, name), local_tmp.name)
                out.append((name, local_tmp.name))
            return out
        finally:
            client.close()

    def remove_result(self, remote_name):
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            _ensure_dir(sftp, self.results_processed_dir)
            sftp.rename(
                posixpath.join(self.results_dir, remote_name),
                posixpath.join(self.results_processed_dir, remote_name),
            )
        finally:
            client.close()
