import random
import string
import time
from firebase_backend import FirebaseBackend
import requests
import json

# --- Ustawienia ---
ADMIN_EMAIL = "admin@domena.pl"
USER_EMAIL_TEMPLATE = "user{:03}@domena.pl"
USER_COUNT = 70
PASSWORD_LENGTH = 14
CREDENTIALS_FILE = "users_credentials.txt"

# --- Funkcje pomocnicze ---
def strong_password(length=PASSWORD_LENGTH):
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.<>/?"
    while True:
        pwd = ''.join(random.choices(chars, k=length))
        if (any(c.islower() for c in pwd) and
            any(c.isupper() for c in pwd) and
            any(c.isdigit() for c in pwd) and
            any(c in "!@#$%^&*()-_=+[]{};:,.<>/?" for c in pwd)):
            return pwd

def add_admin_uid_to_meta(admin_uid, backend):
    """
    Dodaje UID admina do dokumentu meta/admins (pole array uids).
    Najpierw próba przez Admin SDK (bez reguł), potem REST (wymaga już roli admin w regułach – dla bootstrapu używamy Admin SDK).
    """
    # Spróbuj Admin SDK (preferowane – omija reguły)
    if backend.admin_add_admin_uid(admin_uid):
        print("[i] UID admina dodany (Admin SDK) do meta/admins.")
        return
    # Fallback REST (działa tylko jeśli konto już ma rolę admin zgodnie z regułami)
    pid = backend.get_project_id()
    url = f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents/meta/admins"
    headers = backend._auth_header()
    # Pobierz aktualny dokument
    res, err = backend._rest("GET", url, headers=headers)
    uids = []
    if not err and res and "fields" in res:
        fields = backend._decode_fields(res["fields"])
        uids = fields.get("uids", []) if isinstance(fields.get("uids"), list) else []
    if admin_uid not in uids:
        uids.append(admin_uid)
    body = {"fields": backend._encode_fields({"uids": uids})}
    _, err2 = backend._rest("PATCH", url, json_body=body, headers=headers)
    if err2:
        print(f"[!] Błąd zapisu meta/admins (REST): {err2}")
    else:
        print(f"[i] UID admina dodany (REST) do meta/admins.")

def ensure_user_doc(backend, email, role):
    """
    Zapewnia istnienie dokumentu użytkownika w Firestore.
    Przy pierwszym logowaniu tworzy dokument, później tylko aktualizuje rolę i aktywność.
    """
    uid = backend.session.get("uid")
    if not uid:
        return
    doc = backend.get_user_doc(uid)
    hwid = backend.compute_hwid()
    user_doc = {
        "email": email,
        "role": role,
        "active": True,
        "hwid": hwid,
        "first_login": False,
    }
    if not doc:
        backend.update_user_fields(uid, user_doc)
    else:
        # Uaktualnij tylko rolę i aktywność
        backend.update_user_fields(uid, {"role": role, "active": True})

def reset_password_and_login(backend, uid, email, new_password):
    # Reset hasła przez Admin SDK, potem logowanie nowym hasłem
    reset_ok = backend.admin_reset_password(uid)
    if reset_ok:
        ok, msg = backend.login(email, reset_ok)
        if ok:
            return reset_ok, True
        else:
            print(f"[!] Błąd logowania po resecie {email}: {msg}")
            return None, False
    else:
        print(f"[!] Nie udało się zresetować hasła dla {email}")
        return None, False

# --- Główna logika ---
def main():
    backend = FirebaseBackend()
    print("[DEBUG] Wynik backend.get_admin_uids():", backend.get_admin_uids())
    credentials = []

    # --- Tworzenie admina ---
    admin_password = strong_password()
    ok, msg = backend.signup(ADMIN_EMAIL, admin_password)
    if not ok and "EMAIL_EXISTS" in msg:
        # Konto już istnieje, reset hasła przez Admin SDK
        admin_uid = backend.admin_get_uid_by_email(ADMIN_EMAIL)
        if admin_uid:
            new_pass = backend.admin_reset_password(admin_uid)
            if new_pass:
                admin_password = new_pass
                ok, msg = backend.login(ADMIN_EMAIL, admin_password)
            else:
                print("[!] Nie udało się zresetować hasła admina.")
                return
        else:
            print("[!] Nie znaleziono UID admina (Admin SDK).")
            return
    elif not ok:
        print(f"[!] Błąd tworzenia admina: {msg}")
        return
    admin_uid = backend.session.get("uid") or backend.admin_get_uid_by_email(ADMIN_EMAIL)
    if not admin_uid:
        print("[!] Nie udało się ustalić UID admina po logowaniu.")
        return
    # Ustaw rolę admina i dodaj do meta
    ensure_user_doc(backend, ADMIN_EMAIL, "admin")
    backend.update_user_fields(admin_uid, {"role": "admin"})
    add_admin_uid_to_meta(admin_uid, backend)
    print("[DEBUG] Lista adminów po dodaniu:", backend.get_admin_uids())
    credentials.append((ADMIN_EMAIL, admin_password, "admin"))
    print(f"[ADMIN] {ADMIN_EMAIL} | {admin_password}")

    # --- Tworzenie użytkowników ---
    for i in range(1, USER_COUNT + 1):
        email = USER_EMAIL_TEMPLATE.format(i)
        password = strong_password()
        ok, msg = backend.signup(email, password)
        if not ok and "EMAIL_EXISTS" in msg:
            print(f"[INFO] Konto {email} już istnieje – resetuję hasło przez Admin SDK. (Oryg. msg: {msg})")
            uid = backend.admin_get_uid_by_email(email)
            if uid:
                new_pass = backend.admin_reset_password(uid)
                if new_pass:
                    password = new_pass
                    ok, msg = backend.login(email, password)
                    if not ok:
                        print(f"[!] Nie udało się zalogować po resecie {email}: {msg}")
                        continue
                else:
                    print(f"[!] Nie udało się zresetować hasła {email}.")
                    continue
            else:
                print(f"[!] Admin SDK nie zwrócił UID dla {email}.")
                continue
        elif not ok:
            print(f"[!] Błąd tworzenia {email}: {msg}")
            continue
        ensure_user_doc(backend, email, "user")
        credentials.append((email, password, "user"))
        print(f"[USER] {email} | {password}")
        time.sleep(0.15)

    # --- Zapisz dane do pliku ---
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        for email, password, role in credentials:
            f.write(f"{email};{password};{role}\n")
    print(f"\n[i] Gotowe! Dane zapisane w {CREDENTIALS_FILE}")

if __name__ == "__main__":
    main()
