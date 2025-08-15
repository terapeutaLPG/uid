import json
import os
import time
import uuid
import platform
import hashlib
import random
import string
import sys  # dodano do obsługi ścieżki w pakiecie PyInstaller
from typing import Any, Dict, Optional, Tuple, List

import requests

# Firebase Admin SDK for admin-only features
try:
    import firebase_admin
    from firebase_admin import credentials, auth as admin_auth, firestore as admin_fs
except Exception:
    firebase_admin = None
    credentials = None
    admin_auth = None
    admin_fs = None


APP_NAME = "MinecraftUUIDTool"
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.getcwd()), APP_NAME)
LOCAL_CONFIG_FILE = os.path.join(os.getcwd(), "config.json")
APPDATA_CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")


class FirebaseBackend:
    def __init__(self):
        self.session: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {}
        self._admin_initialized = False
        self._admin_db = None
        self._admin_last_error = ""  # przechowywanie ostatniego błędu inicjalizacji Admin SDK
        self._load_and_merge_config()

    # --------------- Config -----------------
    def _ensure_appdata_dir(self):
        os.makedirs(APPDATA_DIR, exist_ok=True)

    def _load_json(self, path: str) -> Dict[str, Any]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_json(self, path: str, data: Dict[str, Any]):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_and_merge_config(self):
        # ...existing code before merge...
        self._ensure_appdata_dir()
        local_cfg = self._load_json(LOCAL_CONFIG_FILE)
        appdata_cfg = self._load_json(APPDATA_CONFIG_FILE)
        merged = local_cfg.copy()
        for k, v in appdata_cfg.items():
            merged[k] = v
        # Domyślne klucze
        merged.setdefault("project_id", "")
        merged.setdefault("web_api_key", "")
        merged.setdefault("service_account_file", "firebase-key.json")
        # Stary pojedynczy webhook zachowany jako fallback
        merged.setdefault("default_discord_webhook", "")
        # Nowe dedykowane webhooki (wyniki i logi) – jeśli brak ustaw domyślne wartości z polecenia
        merged.setdefault("discord_webhook_results", "https://discord.com/api/webhooks/1405588853921677455/WCMil5g2ZXq8xbL-0mO1Hx23oLf-rpa_4DAF6BsrPebORQu6XBMctiyKtwAPW_YFiDhc")
        merged.setdefault("discord_webhook_logs", "https://discord.com/api/webhooks/1405879617688043531/jBI8yM0pcvV45YJ2gXLl1Z1kzxmH6zR-MBIUmLDNkOSDXP-lLgtrRDzC3U1ijd50Cd3P")
        merged.setdefault("session", {"refresh_token": "", "id_token": "", "expires_at": 0, "uid": "", "email": ""})
        # Uzupełnienie braków w istniejącej sesji
        sess = merged.get("session", {})
        sess.setdefault("refresh_token", "")
        sess.setdefault("id_token", "")
        sess.setdefault("expires_at", 0)
        sess.setdefault("uid", "")
        sess.setdefault("email", "")
        merged["session"] = sess
        self.config = merged
        self.session = merged.get("session", {})
        self._save_json(APPDATA_CONFIG_FILE, self.config)

    def _save_app_config(self):
        self.config["session"] = self.session
        self._save_json(APPDATA_CONFIG_FILE, self.config)

    # --------------- Helpers -----------------
    def get_project_id(self) -> str:
        return self.config.get("project_id", "").strip()

    def get_api_key(self) -> str:
        return self.config.get("web_api_key", "")

    def get_service_account_file(self) -> str:
        # Preferowana nazwa z configu
        candidate = self.config.get("service_account_file", "firebase-key.json") or "firebase-key.json"
        # Jeśli absolutna i istnieje
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        # Katalog roboczy (tam gdzie uruchomiono exe / skrypt)
        cwd_path = os.path.join(os.getcwd(), os.path.basename(candidate))
        if os.path.exists(cwd_path):
            return cwd_path
        # Katalog tymczasowy PyInstaller (onefile)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundle_path = os.path.join(meipass, os.path.basename(candidate))
            if os.path.exists(bundle_path):
                return bundle_path
        # %APPDATA% (APPDATA_DIR)
        appdata_path = os.path.join(APPDATA_DIR, os.path.basename(candidate))
        if os.path.exists(appdata_path):
            return appdata_path
        # Ostatecznie zwróć nazwę (może nie istnieć – zostanie obsłużone)
        return cwd_path

    # --- Webhook helpers ---
    def get_discord_webhook_results(self) -> str:
        return self.config.get("discord_webhook_results") or self.config.get("default_discord_webhook", "")

    def set_discord_webhook_results(self, url: str):
        self.config["discord_webhook_results"] = url
        self._save_app_config()

    def get_discord_webhook_logs(self) -> str:
        return self.config.get("discord_webhook_logs", "")

    def set_discord_webhook_logs(self, url: str):
        self.config["discord_webhook_logs"] = url
        self._save_app_config()

    # --------------- Helpers (cont'd) -----------------
    def get_discord_webhook(self) -> str:
        # Pozostawione dla starych wywołań – zwraca webhook wyników
        return self.get_discord_webhook_results()

    def set_discord_webhook(self, url: str):
        self.set_discord_webhook_results(url)

    def get_discord_webhook_fallback(self) -> str:
        # Zachowana dla kompatybilności wstecznej
        return self.config.get("default_discord_webhook", "")

    # --------------- HWID -----------------
    def compute_hwid(self) -> str:
        base = f"{uuid.getnode()}|{platform.system()}|{platform.machine()}|{platform.version()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    # --------------- Auth (REST) -----------------
    def _rest(self, method: str, url: str, json_body: Optional[dict] = None, headers: Optional[dict] = None) -> Tuple[Optional[dict], Optional[str]]:
        try:
            resp = requests.request(method, url, json=json_body, headers=headers, timeout=30)
            if resp.status_code >= 200 and resp.status_code < 300:
                if resp.text:
                    return resp.json(), None
                else:
                    return {}, None
            else:
                try:
                    err = resp.json()
                except Exception:
                    err = {"error": resp.text}
                return None, f"HTTP {resp.status_code}: {err}"
        except Exception as e:
            return None, str(e)

    def signup(self, email: str, password: str) -> Tuple[bool, str]:
        key = self.get_api_key()
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={key}"
        data = {"email": email, "password": password, "returnSecureToken": True}
        res, err = self._rest("POST", url, json_body=data)
        if err:
            up = err.upper()
            if "EMAIL_EXISTS" in up:
                return False, "Email już istnieje."
            if "TOO_MANY_ATTEMPTS_TRY_LATER" in up:
                return False, "Zbyt wiele prób. Spróbuj ponownie później."
            return False, f"Rejestracja nie powiodła się: {err}"
        # Create Firestore user doc (own doc) via REST with idToken
        self.session["id_token"] = res.get("idToken", "")
        self.session["refresh_token"] = res.get("refreshToken", "")
        self.session["expires_at"] = int(time.time()) + int(res.get("expiresIn", "3600")) - 60
        self.session["uid"] = res.get("localId", "")
        self.session["email"] = email  # zapisz email
        self._save_app_config()
        # Initialize user document
        hwid = self.compute_hwid()
        now_iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        user_doc = {
            "email": email,
            "role": "user",
            "active": True,
            "hwid": hwid,
            "first_login": True,
            "first_login_at": now_iso,
        }
        self._set_user_doc_rest(self.session["uid"], user_doc)
        return True, "OK"

    def login(self, email: str, password: str) -> Tuple[bool, str]:
        key = self.get_api_key()
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
        data = {"email": email, "password": password, "returnSecureToken": True}
        res, err = self._rest("POST", url, json_body=data)
        if err:
            lowered = err.upper()
            if ("INVALID_PASSWORD" in lowered or
                "EMAIL_NOT_FOUND" in lowered or
                "INVALID_LOGIN_CREDENTIALS" in lowered):
                return False, "Błędny email lub hasło."
            if "USER_DISABLED" in lowered:
                return False, "Konto wyłączone. Skontaktuj się z administratorem."
            return False, f"Logowanie nie powiodła się: {err}"
        self.session["id_token"] = res.get("idToken", "")
        self.session["refresh_token"] = res.get("refreshToken", "")
        self.session["expires_at"] = int(time.time()) + int(res.get("expiresIn", "3600")) - 60
        self.session["uid"] = res.get("localId", "")
        self.session["email"] = email
        self._save_app_config()
        self._post_login_checks()
        ok, policy_msg = self._account_policy_check()
        if not ok:
            self.logout()
            return False, policy_msg
        # Wysłanie logu logowania
        try:
            doc = self.get_user_doc(self.session.get("uid", "") or "") or {}
            hwid = doc.get("hwid", "")
            first_login_at = doc.get("first_login_at", "-")
            payload = {
                "embeds": [
                    {
                        "title": "Logowanie użytkownika",
                        "color": 3447003,
                        "fields": [
                            {"name": "Email", "value": email, "inline": True},
                            {"name": "HWID", "value": hwid or "-", "inline": False},
                            {"name": "Pierwsze logowanie", "value": first_login_at or "-", "inline": True},
                            {"name": "Czas teraz", "value": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), "inline": True},
                        ],
                    }
                ]
            }
            self.send_log_webhook(payload)
        except Exception:
            pass
        return True, "OK"

    def refresh_session(self) -> bool:
        key = self.get_api_key()
        refresh_token = self.session.get("refresh_token", "")
        if not refresh_token:
            return False
        url = f"https://securetoken.googleapis.com/v1/token?key={key}"
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        res, err = self._rest("POST", url, json_body=data)
        if err:
            return False
        self.session["id_token"] = res.get("id_token", "")
        self.session["refresh_token"] = res.get("refresh_token", refresh_token)
        self.session["expires_at"] = int(time.time()) + int(res.get("expires_in", "3600")) - 60
        self.session["uid"] = res.get("user_id", self.session.get("uid", ""))
        # email może być nieznany – pozostaw jeśli istnieje
        self._save_app_config()
        return True

    def logout(self):
        # Wyczyszczenie wszystkich istotnych pól sesji
        self.session = {"refresh_token": "", "id_token": "", "expires_at": 0, "uid": "", "email": ""}
        self._save_app_config()

    def get_id_token(self) -> Optional[str]:
        now = int(time.time())
        if self.session.get("id_token") and now < int(self.session.get("expires_at", 0)):
            return self.session.get("id_token")
        if self.refresh_session():
            return self.session.get("id_token")
        return None

    def get_user_email_from_token(self) -> Optional[str]:
        # Minimal token lookup via identitytoolkit getAccountInfo
        key = self.get_api_key()
        id_token = self.get_id_token()
        if not id_token:
            return None
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={key}"
        res, err = self._rest("POST", url, json_body={"idToken": id_token})
        if err:
            return None
        users = res.get("users", [])
        if users:
            return users[0].get("email")
        return None

    def get_saved_email(self) -> str:
        """Zwraca zapamiętany email; jeśli brak – próbuje odczytać z tokena i zapisać."""
        email = self.session.get("email", "")
        if email:
            return email
        looked = self.get_user_email_from_token() or ""
        if looked:
            self.session["email"] = looked
            self._save_app_config()
        return looked

    def has_saved_credentials(self) -> bool:
        """Czy mamy zapamiętany refresh_token (i potencjalnie email) do auto‑logowania."""
        return bool(self.session.get("refresh_token"))

    # --------------- Firestore (REST, typed) -----------------
    def _fs_rest_path(self) -> str:
        pid = self.get_project_id()
        return f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents"

    @staticmethod
    def _encode_fields(data: Dict[str, Any]) -> Dict[str, Any]:
        def enc(v: Any) -> Dict[str, Any]:
            if isinstance(v, bool):
                return {"booleanValue": v}
            if isinstance(v, int):
                return {"integerValue": str(v)}
            if isinstance(v, float):
                return {"doubleValue": v}
            if isinstance(v, dict):
                return {"mapValue": {"fields": FirebaseBackend._encode_fields(v)}}
            if isinstance(v, list):
                return {"arrayValue": {"values": [enc(x) for x in v]}}
            if v is None:
                return {"nullValue": None}
            return {"stringValue": str(v)}
        return {k: enc(v) for k, v in data.items()}

    @staticmethod
    def _decode_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
        def dec(v: Dict[str, Any]) -> Any:
            if "stringValue" in v:
                return v["stringValue"]
            if "booleanValue" in v:
                return v["booleanValue"]
            if "integerValue" in v:
                try:
                    return int(v["integerValue"])
                except Exception:
                    return int(float(v["integerValue"]))
            if "doubleValue" in v:
                return float(v["doubleValue"])
            if "nullValue" in v:
                return None
            if "arrayValue" in v:
                return [dec(x) for x in v["arrayValue"].get("values", [])]
            if "mapValue" in v:
                return FirebaseBackend._decode_fields(v["mapValue"].get("fields", {}))
            return v
        return {k: dec(v) for k, v in fields.items()} if fields else {}

    def _auth_header(self) -> Dict[str, str]:
        token = self.get_id_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_user_doc(self, uid: str) -> Optional[Dict[str, Any]]:
        url = f"{self._fs_rest_path()}/users/{uid}"
        res, err = self._rest("GET", url, headers=self._auth_header())
        if err:
            return None
        fields = res.get("fields", {})
        return self._decode_fields(fields)

    def update_user_fields(self, uid: str, data: Dict[str, Any]) -> bool:
        # Patch merge
        url = f"{self._fs_rest_path()}/users/{uid}?updateMask.fieldPaths=" + "&updateMask.fieldPaths=".join([requests.utils.quote(k, safe='') for k in data.keys()])
        body = {"fields": self._encode_fields(data)}
        res, err = self._rest("PATCH", url, json_body=body, headers=self._auth_header())
        return err is None

    def _set_user_doc_rest(self, uid: str, data: Dict[str, Any]) -> bool:
        url = f"{self._fs_rest_path()}/users/{uid}"
        body = {"fields": self._encode_fields(data)}
        res, err = self._rest("PATCH", url, json_body=body, headers=self._auth_header())
        return err is None

    def get_admin_uids(self) -> List[str]:
        # Uproszczona struktura: dokument meta/admins z polem uids: array<string>
        url = f"{self._fs_rest_path()}/meta/admins"
        res, err = self._rest("GET", url, headers=self._auth_header())
        print(f"[DEBUG] Firestore response for admin uids: {res}, error: {err}")
        if err:
            return []
        fields = self._decode_fields(res.get("fields", {}))
        print(f"[DEBUG] Decoded fields for admin uids: {fields}")
        return fields.get("uids", []) if isinstance(fields.get("uids"), list) else []

    def admin_add_admin_uid(self, uid: str) -> bool:
        """Dodaje UID do listy adminów (admin context) z logami debug."""
        if not self._init_admin():
            print("[DEBUG] Admin SDK nie zainicjalizowany.")
            return False
        try:
            doc_ref = self._admin_db.collection("meta").document("admins")
            doc = doc_ref.get()
            uids: List[str] = []
            if doc.exists:
                data = doc.to_dict() or {}
                print("[DEBUG] Bieżący dokument meta/admins (Admin SDK):", data)
                if isinstance(data.get("uids"), list):
                    uids = list({str(x) for x in data.get("uids")})
            if uid not in uids:
                uids.append(uid)
            doc_ref.set({"uids": uids}, merge=True)
            # Odczyt po zapisie
            new_doc = doc_ref.get()
            print("[DEBUG] Dokument meta/admins po zapisie:", new_doc.to_dict())
            return True
        except Exception as e:
            print("[DEBUG] Błąd admin_add_admin_uid:", e)
            return False

    def admin_delete_user(self, uid: str) -> Tuple[bool, str]:
        """Usuwa użytkownika (Auth + Firestore dokument)."""
        if not self._init_admin():
            return False, "Brak Admin SDK"
        try:
            # Usuń dokument Firestore
            try:
                self._admin_db.collection("users").document(uid).delete()
            except Exception:
                pass
            # Usuń z listy adminów jeśli jest
            try:
                doc_ref = self._admin_db.collection("meta").document("admins")
                doc = doc_ref.get()
                if doc.exists:
                    data = doc.to_dict() or {}
                    uids = data.get("uids", [])
                    if isinstance(uids, list) and uid in uids:
                        uids.remove(uid)
                        doc_ref.set({"uids": uids}, merge=True)
            except Exception:
                pass
            # Usuń konto auth
            try:
                admin_auth.delete_user(uid)
            except Exception:
                pass
            return True, "OK"
        except Exception as e:
            return False, f"Błąd: {e}"

    def admin_clear_hwid(self, uid: str) -> Tuple[bool, str]:
        """Czyści HWID użytkownika, pozwalając na ponowne przypisanie przy kolejnym logowaniu."""
        if not self._init_admin():
            return False, "Brak Admin SDK"
        try:
            self._admin_db.collection("users").document(uid).set({"hwid": "", "first_login": True}, merge=True)
            return True, "OK"
        except Exception as e:
            return False, f"Błąd: {e}"

    # --------------- Admin SDK (optional) -----------------
    def _init_admin(self) -> bool:
        if self._admin_initialized:
            return True
        if firebase_admin is None:
            self._admin_last_error = "Brak biblioteki firebase_admin w środowisku."
            print("[DEBUG] firebase_admin brak.")
            return False
        try:
            if firebase_admin._apps:  # type: ignore
                self._admin_db = admin_fs.client()
                self._admin_initialized = True
                self._admin_last_error = ""
                print("[DEBUG] Reuse istniejącej instancji Firebase Admin.")
                return True
            cred_path = self.get_service_account_file()
            if not os.path.exists(cred_path):
                self._admin_last_error = f"Nie znaleziono pliku service account: {cred_path}"
                print("[DEBUG] Brak pliku service account:", cred_path)
                return False
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {"projectId": self.get_project_id()})
            self._admin_db = admin_fs.client()
            self._admin_initialized = True
            self._admin_last_error = ""
            print("[DEBUG] Inicjalizacja Firebase Admin OK.")
            return True
        except Exception as e:
            self._admin_last_error = f"Błąd inicjalizacji Admin SDK: {e}"
            print("[DEBUG] _init_admin błąd:", e)
            try:
                if firebase_admin._apps:  # type: ignore
                    self._admin_db = admin_fs.client()
                    self._admin_initialized = True
                    self._admin_last_error = ""
                    print("[DEBUG] Fallback reuse instancji po wyjątku.")
                    return True
            except Exception:
                pass
            return False

    def _admin_list_users_rest(self) -> List[Dict[str, Any]]:
        """Fallback: pobiera dokumenty z kolekcji users przez REST gdy Admin SDK niedostępny."""
        token_hdr = self._auth_header()
        if not token_hdr:
            return []
        url = f"{self._fs_rest_path()}/users?pageSize=300"
        res, err = self._rest("GET", url, headers=token_hdr)
        if err or not res:
            return []
        docs = res.get("documents", [])
        out: List[Dict[str, Any]] = []
        for d in docs:
            fields = d.get("fields", {})
            data = self._decode_fields(fields)
            # name: projects/<pid>/databases/(default)/documents/users/<id>
            name_path = d.get("name", "")
            doc_id = name_path.rsplit("/", 1)[-1] if "/" in name_path else name_path
            data["id"] = doc_id
            out.append(data)
        return out

    def admin_list_users(self) -> List[Dict[str, Any]]:
        if self._init_admin():
            try:
                docs = self._admin_db.collection("users").stream()
                result = []
                for d in docs:
                    data = d.to_dict() or {}
                    data["id"] = d.id
                    result.append(data)
                return result
            except Exception as e:
                self._admin_last_error = f"Błąd odczytu Admin SDK: {e}"
        # Fallback REST
        rest_users = self._admin_list_users_rest()
        if not rest_users and not self._admin_last_error:
            self._admin_last_error = "Brak danych (REST) lub brak uprawnień (sprawdź rolę admin)."
        return rest_users

    def admin_list_users(self) -> List[Dict[str, Any]]:
        if self._init_admin():
            try:
                docs = self._admin_db.collection("users").stream()
                result = []
                for d in docs:
                    data = d.to_dict() or {}
                    data["id"] = d.id
                    result.append(data)
                return result
            except Exception as e:
                self._admin_last_error = f"Błąd odczytu Admin SDK: {e}"
        # Fallback REST
        rest_users = self._admin_list_users_rest()
        if not rest_users and not self._admin_last_error:
            self._admin_last_error = "Brak danych (REST) lub brak uprawnień (sprawdź rolę admin)."
        return rest_users

    def admin_set_user_role_active(self, uid: str, role: str, active: bool) -> bool:
        if not self._init_admin():
            return False
        try:
            self._admin_db.collection("users").document(uid).set({"role": role, "active": bool(active)}, merge=True)
            return True
        except Exception:
            return False

    def admin_reset_password(self, uid: str) -> Optional[str]:
        # Generates a random password and sets it using Admin SDK
        if not self._init_admin():
            return None
        try:
            new_pass = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            admin_auth.update_user(uid, password=new_pass)
            return new_pass
        except Exception:
            return None

    def admin_get_webhook(self) -> str:
        if not self._init_admin():
            return self.get_discord_webhook()
        try:
            doc = self._admin_db.collection("meta").document("webhooks").get()
            if doc.exists:
                data = doc.to_dict() or {}
                return data.get("discord", "")
        except Exception:
            pass
        return ""

    def admin_set_webhook(self, url: str) -> bool:
        if not self._init_admin():
            # Fallback: store locally only
            self.set_discord_webhook(url)
            return True
        try:
            self._admin_db.collection("meta").document("webhooks").set({"discord": url}, merge=True)
            # Also persist locally for convenience
            self.set_discord_webhook(url)
            return True
        except Exception:
            return False

    def admin_get_uid_by_email(self, email: str) -> Optional[str]:
        if not self._init_admin():
            return None
        try:
            user = admin_auth.get_user_by_email(email)
            return user.uid
        except Exception:
            return None

    def admin_create_user(self, email: str, password: str, role: str = "user", active: bool = True) -> Tuple[bool, str, Optional[str]]:
        """Tworzy użytkownika przez Admin SDK z pominięciem limitów signup.
        Zwraca (ok, msg, uid)."""
        if not self._init_admin():
            return False, "Brak inicjalizacji Admin SDK.", None
        try:
            user = admin_auth.create_user(email=email, password=password)
            uid = user.uid
            doc = {
                "email": email,
                "role": role,
                "active": bool(active),
                "hwid": "",
                "first_login": True,
            }
            try:
                self._admin_db.collection("users").document(uid).set(doc, merge=True)
            except Exception:
                pass
            return True, "OK", uid
        except admin_auth.EmailAlreadyExistsError:  # type: ignore
            return False, "Email już istnieje.", None
        except Exception as e:
            return False, f"Błąd tworzenia: {e}", None

    def admin_create_or_update(self, email: str, password: Optional[str], role: str = "user", active: bool = True) -> Tuple[bool, str, Optional[str]]:
        """Tworzy użytkownika jeśli nie istnieje (Admin SDK) lub aktualizuje rolę/aktywność jeśli istnieje.
        Jeśli password jest None przy istniejącym użytkowniku – nie zmienia hasła."""
        if not self._init_admin():
            return False, "Brak Admin SDK", None
        try:
            try:
                user = admin_auth.get_user_by_email(email)
                uid = user.uid
                # Aktualizacja hasła jeśli podano
                if password:
                    admin_auth.update_user(uid, password=password)
            except Exception:
                if not password:
                    password = ''.join(random.choices(string.ascii_letters + string.digits, k=14))
                user = admin_auth.create_user(email=email, password=password)
                uid = user.uid
            # Firestore doc upsert
            doc = {
                "email": email,
                "role": role,
                "active": bool(active),
            }
            try:
                self._admin_db.collection("users").document(uid).set(doc, merge=True)
            except Exception:
                pass
            # Dodaj do meta/admins jeśli rola admin
            if role == "admin":
                self.admin_add_admin_uid(uid)
            return True, "OK", uid
        except Exception as e:
            return False, f"Błąd: {e}", None

    def sync_users_from_file(self, path: str) -> Tuple[int, int, List[str]]:
        """Synchronizuje konta z pliku (email;haslo;rola). Zwraca (utworzonych, zaktualizowanych, logi).
        Przy braku hasła lub roli dopuszczalne formaty: email;haslo;rola | email;haslo | email.
        Rola default 'user'."""
        created = 0
        updated = 0
        logs: List[str] = []
        if not os.path.exists(path):
            return 0, 0, [f"Brak pliku: {path}"]
        if not self._init_admin():
            return 0, 0, ["Brak inicjalizacji Admin SDK."]
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(";") if p.strip()]
                if not parts:
                    continue
                email = parts[0]
                password = None
                role = "user"
                if len(parts) >= 2:
                    password = parts[1]
                if len(parts) >= 3:
                    role = parts[2]
                ok = False
                try:
                    user = admin_auth.get_user_by_email(email)  # type: ignore
                    # istnieje
                    ok, msg, uid = self.admin_create_or_update(email, password, role=role, active=True)
                    if ok:
                        updated += 1
                        logs.append(f"Zaktualizowano: {email} ({role})")
                    else:
                        logs.append(f"Błąd aktualizacji {email}: {msg}")
                except Exception:
                    # tworzymy
                    if not password:
                        password = ''.join(random.choices(string.ascii_letters + string.digits, k=14))
                    ok, msg, uid = self.admin_create_or_update(email, password, role=role, active=True)
                    if ok:
                        created += 1
                        logs.append(f"Utworzono: {email} ({role})")
                    else:
                        logs.append(f"Błąd tworzenia {email}: {msg}")
        return created, updated, logs

    # --------------- Discord Webhook -----------------
    def send_discord_webhook(self, content: Dict[str, Any], override_url: Optional[str] = None) -> Tuple[bool, str]:
        # Zachowana stara metoda jako ogólny fallback (użyje webhooka wyników jeśli brak override)
        url = (override_url or self.admin_get_webhook() or self.get_discord_webhook_results() or self.get_discord_webhook())
        if not url:
            return False, "Brak ustawionego webhooka Discord."
        try:
            r = requests.post(url, json=content, timeout=20)
            if 200 <= r.status_code < 300:
                return True, "OK"
            return False, f"Discord HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def send_result_webhook(self, content: Dict[str, Any]) -> Tuple[bool, str]:
        url = self.get_discord_webhook_results().strip()
        if not url:
            return False, "Brak webhooka wyników."
        try:
            r = requests.post(url, json=content, timeout=20)
            if 200 <= r.status_code < 300:
                return True, "OK"
            return False, f"Discord HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def send_log_webhook(self, content: Dict[str, Any]) -> Tuple[bool, str]:
        url = self.get_discord_webhook_logs().strip()
        if not url:
            return False, "Brak webhooka logów."
        try:
            r = requests.post(url, json=content, timeout=20)
            if 200 <= r.status_code < 300:
                return True, "OK"
            return False, f"Discord HTTP {r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    # --------------- Minecraft UUID -----------------
    @staticmethod
    def uuid_to_str(u: uuid.UUID) -> str:
        return str(u)

    @staticmethod
    def offline_uuid(username: str) -> str:
        # Java Offline UUID algorithm: UUID.nameUUIDFromBytes("OfflinePlayer:" + username)
        name = ("OfflinePlayer:" + username).encode("utf-8")
        md5 = hashlib.md5(name).digest()
        as_list = list(md5)
        as_list[6] = (as_list[6] & 0x0F) | 0x30  # version 3
        as_list[8] = (as_list[8] & 0x3F) | 0x80  # IETF variant
        u = uuid.UUID(bytes=bytes(as_list))
        return str(u)

    @staticmethod
    def premium_uuid(username: str) -> Tuple[Optional[str], Optional[str]]:
        # Returns (uuid, error)
        try:
            r = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{username}", timeout=20)
            if r.status_code == 204:
                return None, "Nie znaleziono konta Premium."
            if r.status_code != 200:
                return None, f"Mojang HTTP {r.status_code}: {r.text}"
            data = r.json()
            raw = data.get("id", "")
            if len(raw) == 32:
                # Insert dashes
                return str(uuid.UUID(raw)), None
            return raw, None
        except Exception as e:
            return None, str(e)

    def auto_uuid(self, username: str) -> Tuple[str, str]:
        u, err = self.premium_uuid(username)
        if u:
            return u, "premium"
        return self.offline_uuid(username), "offline"
    def _post_login_checks(self):
        uid = self.session.get("uid")
        if not uid:
            return
        doc = self.get_user_doc(uid)
        hwid = self.compute_hwid()
        now_iso = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        if not doc:
            email = self.get_user_email_from_token() or self.session.get("email", "")
            user_doc = {
                "email": email,
                "role": "user",
                "active": True,
                "hwid": hwid,
                "first_login": True,
                "first_login_at": now_iso,
            }
            self._set_user_doc_rest(uid, user_doc)
            doc = user_doc
        else:
            changed = False
            if not doc.get("hwid"):
                doc["hwid"] = hwid
                changed = True
            if not doc.get("first_login_at"):
                doc["first_login_at"] = now_iso
                changed = True
            if changed:
                self._set_user_doc_rest(uid, doc)
        admins = self.get_admin_uids()
        if admins and uid in admins and doc.get("role") != "admin":
            self.update_user_fields(uid, {"role": "admin"})

    def _account_policy_check(self) -> Tuple[bool, str]:
        # Miejsce na dodatkowe reguły (np. aktywność, ban itp.)
        uid = self.session.get("uid")
        if not uid:
            return False, "Brak UID sesji."
        doc = self.get_user_doc(uid) or {}
        if not doc.get("active", True):
            return False, "Konto nieaktywne."
        if doc.get("role") == "banned":
            return False, "Konto zbanowane."
        return True, "OK"
    def debug_admin_env(self) -> Dict[str, Any]:
        """Zwraca diagnostykę inicjalizacji Admin SDK (ścieżki, istnieje plik, projekt, ostatni błąd)."""
        path = self.get_service_account_file()
        return {
            "project_id": self.get_project_id(),
            "service_account_resolved_path": path,
            "service_account_exists": os.path.exists(path),
            "admin_initialized": self._admin_initialized,
            "last_error": self._admin_last_error,
            "firebase_admin_imported": firebase_admin is not None,
        }
if __name__ == "__main__":
    # Prosty smoke-test: tylko inicjalizacja backendu
    fb = FirebaseBackend()
    print("[DEBUG] Inicjalizacja zakończona. Project ID:", fb.get_project_id())
