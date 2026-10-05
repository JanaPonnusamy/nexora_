"""SFTP receiver transport: the HO half of store_agent/file_transfer/
sftp_transport.py's layout/protocol. Requires the optional 'paramiko'
dependency (guarded import). Authentication is by private key or password,
both read from environment variables named in config -- never hardcoded.
"""
import os
import posixpath
import tempfile

from modules.sync.file_transfer_transport.base import ReceiverTransport


class SftpConfigError(RuntimeError):
    pass


def _connect(cfg):
    try:
        import paramiko
    except ImportError as ex:
        raise SftpConfigError(
            "SFTP transport requires the 'paramiko' package (pip install paramiko)"
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
        raise SftpConfigError("SFTP transport config requires 'key_path' or 'password_env'")
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


class SftpReceiverTransport(ReceiverTransport):
    def __init__(self, cfg):
        self.cfg = cfg
        self.remote_root = cfg.get("remote_root", "/nexora_sync").rstrip("/")

    def list_incoming(self):
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            inbox_root = posixpath.join(self.remote_root, "inbox")
            out = []
            try:
                store_dirs = sftp.listdir(inbox_root)
            except IOError:
                return []
            for store_id in sorted(store_dirs):
                store_dir = posixpath.join(inbox_root, store_id)
                try:
                    entries = sftp.listdir_attr(store_dir)
                except IOError:
                    continue
                for entry in entries:
                    if not entry.filename.endswith(".zip"):
                        continue
                    local_tmp = tempfile.NamedTemporaryFile(
                        prefix="nexora_pkg_", suffix=".zip", delete=False
                    )
                    local_tmp.close()
                    sftp.get(posixpath.join(store_dir, entry.filename), local_tmp.name)
                    out.append((store_id + "/" + entry.filename, local_tmp.name))
            return out
        finally:
            client.close()

    def archive_incoming(self, remote_name, success):
        store_id, filename = remote_name.split("/", 1)
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            src = posixpath.join(self.remote_root, "inbox", store_id, filename)
            dest_dir = posixpath.join(
                self.remote_root, "inbox", store_id,
                "processed" if success else "quarantine",
            )
            _ensure_dir(sftp, dest_dir)
            sftp.rename(src, posixpath.join(dest_dir, filename))
        finally:
            client.close()

    def send_result(self, store_id, result_filename, local_path):
        client = _connect(self.cfg)
        try:
            sftp = client.open_sftp()
            dest_dir = posixpath.join(self.remote_root, "results", str(store_id))
            _ensure_dir(sftp, dest_dir)
            remote_tmp = posixpath.join(dest_dir, result_filename + ".part")
            remote_final = posixpath.join(dest_dir, result_filename)
            sftp.put(local_path, remote_tmp)
            sftp.rename(remote_tmp, remote_final)
        finally:
            client.close()
