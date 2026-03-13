import traceback

from cryptography import fernet
from cryptography.fernet import Fernet, MultiFernet


class EncryptManager:
    multi_fernet: MultiFernet | None = None

    def __init__(self, fernet_keys: str):
        fernet_key_list: list[bytes] = []
        fernet_keys_split: list[str] = []
        if fernet_keys:
            fernet_keys_split = fernet_keys.split(",")
        for fernet_key in fernet_keys_split:
            fernet_key = fernet_key.strip()
            if not fernet_key:
                continue
            fernet_key_list += [fernet_key.encode("utf-8")]
        fernets = []
        for k in fernet_key_list:
            try:
                fernets += [Fernet(k)]
            except Exception:  # noqa: S112, PERF203
                continue
        if len(fernets) > 0:
            self.multi_fernet = MultiFernet(fernets)

    def rotate(self, encrypted_value: str) -> str | None:
        if not self.multi_fernet:
            return encrypted_value
        try:
            return self.multi_fernet.rotate(encrypted_value.encode("utf-8")).decode(
                "utf-8"
            )
        except fernet.InvalidToken:
            # Token is no longer valid, just ignore
            return None
        except Exception as e:
            print(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
            return None

    def encrypt(self, value: str) -> str | None:
        if not self.multi_fernet:
            return value
        try:
            return self.multi_fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        except Exception as e:
            print(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
            return None

    def decrypt(self, encrypted_value: str, ttl: int | None = None) -> str | None:
        if not self.multi_fernet:
            return encrypted_value
        try:
            return self.multi_fernet.decrypt(
                encrypted_value.encode("utf-8"), ttl=ttl
            ).decode("utf-8")
        except fernet.InvalidToken:
            # Token is no longer valid, just ignore
            return None
        except Exception as e:
            print(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
            return None
