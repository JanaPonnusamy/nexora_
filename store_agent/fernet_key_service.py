
from pathlib import Path
from cryptography.fernet import Fernet

class FernetKeyService:

    KEY_FILE = Path(__file__).parent / "config" / "fernet.key"

    def generate_key(self):
        return Fernet.generate_key()

    def save_key(self, key):

        self.KEY_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.KEY_FILE.write_bytes(key)

    def load_key(self):

        return self.KEY_FILE.read_bytes()

    def key_exists(self):

        return self.KEY_FILE.exists()
