import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict

import pyperclip

from firebase_backend import FirebaseBackend


class MinecraftUUIDToolApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Minecraft UUID Tool")
        self.root.geometry("780x560")
        self.backend = FirebaseBackend()
        # Stylizacja podstawowa
        try:
            style = ttk.Style()
            # Wybierz preferowany motyw jeśli dostępny
            for theme_candidate in ("azure", "clam", "alt", "default"):
                if theme_candidate in style.theme_names():
                    style.theme_use(theme_candidate)
                    break
            style.configure("TLabel", padding=2)
            style.configure("TButton", padding=4)
            style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        except Exception:
            pass

        # Notebook tworzymy, ale początkowo tylko jedna karta logowania
        self.notebook = ttk.Notebook(self.root)
        self.frame_login = ttk.Frame(self.notebook)
        self.notebook.add(self.frame_login, text="Logowanie")
        self.notebook.pack(expand=True, fill=tk.BOTH)

        # Placeholdery dla późniejszych kart
        self.frame_user = None
        self.frame_admin = None
        self.frame_batch = None

        self._build_login_ui()
        # Atrybut kontrolujący jednorazowy dialog wylogowania
        self.logout_dialog = None

        # Auto‑login jeżeli mamy refresh_token (bez pytania)
        if self.backend.has_saved_credentials():
            # Spróbuj odświeżyć token i przejść dalej
            if self.backend.get_id_token():
                self.login_status.set("Zalogowano automatycznie.")
                self._after_success_login()
            else:
                # Brak ważnego tokena – pokaż login (pola mogą uzupełnić email)
                saved_email = self.backend.get_saved_email()
                if saved_email:
                    self.email_var.set(saved_email)
        else:
            # Brak danych – pozostajemy na ekranie logowania
            pass

        # Atrybuty do inline nick
        self.nick_inline_frame = None
        self.user_nick_var = None

    # ---------------- Login UI ----------------
    def _build_login_ui(self):
        f = self.frame_login
        for c in range(2):
            f.grid_columnconfigure(c, weight=1)
        pad = {"padx": 8, "pady": 6}
        ttk.Label(f, text="Minecraft UUID Tool by jaruso99", style="Header.TLabel").grid(row=0, column=0, columnspan=2, pady=(18, 12))
        ttk.Label(f, text="Email:").grid(row=1, column=0, sticky=tk.E, **pad)
        self.email_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.email_var, width=40).grid(row=1, column=1, sticky=tk.W, **pad)
        ttk.Label(f, text="Hasło:").grid(row=2, column=0, sticky=tk.E, **pad)
        self.pass_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.pass_var, width=40, show="*").grid(row=2, column=1, sticky=tk.W, **pad)
        # Usunięto pole 'Twój nick' – nick można ustawić tylko po zalogowaniu jeśli brak w profilu
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 4))
        ttk.Button(btn_frame, text="Zaloguj", command=self.on_login, width=16).pack(side=tk.LEFT, padx=5)
        self.login_status = tk.StringVar(value="Wprowadź dane logowania.")
        ttk.Label(f, textvariable=self.login_status, foreground="#555").grid(row=4, column=0, columnspan=2, sticky=tk.W, **pad)

    def _ensure_main_tabs(self):
        """Tworzy tylko kartę użytkownika (podstawową)."""
        if self.frame_user is None:
            self.frame_user = ttk.Frame(self.notebook)
            self._build_user_ui()
            self.notebook.add(self.frame_user, text="Użytkownik")

    def _ensure_admin_tabs(self):
        """Tworzy karty administratora i batch wyłącznie dla admina."""
        if self.frame_admin is None:
            self.frame_admin = ttk.Frame(self.notebook)
            self._build_admin_ui()
            self.notebook.add(self.frame_admin, text="Administrator")
        if self.frame_batch is None:
            self.frame_batch = ttk.Frame(self.notebook)
            self._build_batch_ui()
            self.notebook.add(self.frame_batch, text="Batch Offline")

    def _after_success_login(self):
        self._ensure_main_tabs()
        self._refresh_role_and_state()
        if self.frame_user is not None:
            self.notebook.select(self.frame_user)

    def on_login(self):
        email = self.email_var.get().strip()
        password = self.pass_var.get().strip()
        if not email or not password:
            messagebox.showerror("Błąd", "Podaj email i hasło.")
            return
        ok, msg = self.backend.login(email, password)
        if ok:
            self.login_status.set("Zalogowano.")
            self._after_success_login()
        else:
            self.login_status.set(msg)
            messagebox.showerror("Błąd logowania", msg)

    def _add_logout_button(self):
        # Dodaj pasek u góry jeśli brak
        if getattr(self, "logout_bar", None) is None:
            self.logout_bar = ttk.Frame(self.root)
            self.logout_bar.pack(side=tk.TOP, fill=tk.X)
            self.user_meta_var = tk.StringVar(value="Nie zalogowano")
            ttk.Label(self.logout_bar, textvariable=self.user_meta_var).pack(side=tk.LEFT, padx=8)
            # Inline edycja nicku (tworzona, ale domyślnie ukryta)
            self.nick_inline_frame = ttk.Frame(self.logout_bar)
            self.user_nick_var = tk.StringVar()
            ttk.Label(self.nick_inline_frame, text="Nick:").pack(side=tk.LEFT, padx=(4, 2))
            entry = ttk.Entry(self.nick_inline_frame, textvariable=self.user_nick_var, width=18)
            entry.pack(side=tk.LEFT)
            save_btn = ttk.Button(self.nick_inline_frame, text="Zapisz nick", command=self._save_inline_nick)
            save_btn.pack(side=tk.LEFT, padx=4)
            self.nick_inline_frame.pack_forget()  # schowaj na start
            ttk.Button(self.logout_bar, text="Wyloguj", command=self.on_logout).pack(side=tk.RIGHT, padx=8, pady=4)

    # Usunięto dialogowe ustawianie nicku – zastąpione inline
    def _save_inline_nick(self):
        uid = self.backend.session.get("uid")
        if not uid:
            return
        nick = (self.user_nick_var.get() or "").strip()
        if not nick:
            messagebox.showerror("Błąd", "Nick nie może być pusty.")
            return
        if len(nick) > 32:
            messagebox.showerror("Błąd", "Nick maksymalnie 32 znaki.")
            return
        # Zapisujemy nick + ustawiamy first_login False
        ok = self.backend.update_user_fields(uid, {"user_nick": nick, "first_login": False})
        if ok:
            messagebox.showinfo("OK", "Nick zapisany.")
            # Schowaj edytor po zapisie
            try:
                self.nick_inline_frame.pack_forget()
            except Exception:
                pass
            self._refresh_role_and_state()
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać nicku.")

    # ---------------- User UI ----------------
    def _build_user_ui(self):
        f = self.frame_user
        pad = {"padx": 8, "pady": 6}
        # Zachowaj ewentualny globalny pasek, ale dodaj też przycisk w karcie
        self._add_logout_button()
        # Górny wiersz z etykietą roli i przyciskiem Wyloguj (widoczny w karcie)
        top_row = ttk.Frame(f)
        top_row.grid(row=0, column=0, columnspan=5, sticky="ew", **pad)
        top_row.grid_columnconfigure(0, weight=1)
        self.role_label_var = tk.StringVar(value="Rola: - | Status: -")
        ttk.Label(top_row, textvariable=self.role_label_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Button(top_row, text="Wyloguj", command=self.on_logout).grid(row=0, column=1, sticky=tk.E, padx=(12, 0))
        # Reszta pól formularza
        ttk.Label(f, text="Nick Minecraft:").grid(row=1, column=0, sticky=tk.W, **pad)
        self.nick_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.nick_var, width=32).grid(row=1, column=1, sticky=tk.W, **pad)
        ttk.Label(f, text="Tryb:").grid(row=1, column=2, sticky=tk.W, **pad)
        self.mode_var = tk.StringVar(value="Auto")
        ttk.Combobox(f, textvariable=self.mode_var, values=["Auto", "Premium", "Offline"], state="readonly", width=10).grid(row=1, column=3, sticky=tk.W, **pad)
        ttk.Button(f, text="Sprawdź UUID", command=self.on_check_uuid).grid(row=1, column=4, sticky=tk.W, **pad)
        ttk.Label(f, text="UUID:").grid(row=2, column=0, sticky=tk.W, **pad)
        self.uuid_text = tk.Text(f, height=2, width=60)
        self.uuid_text.grid(row=2, column=1, columnspan=3, sticky=tk.W, **pad)
        ttk.Button(f, text="Kopiuj UUID", command=self.on_copy_uuid).grid(row=2, column=4, sticky=tk.W, **pad)
        self.user_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.user_status, foreground="#555").grid(row=3, column=0, columnspan=5, sticky=tk.W, **pad)

    def _refresh_role_and_state(self):
        uid = self.backend.session.get("uid")
        if uid:
            doc = self.backend.get_user_doc(uid) or {}
            role = doc.get("role", "-")
            active = doc.get("active", True)
            email = self.backend.session.get("email", "") or doc.get("email", "")
            first_login_at = doc.get("first_login_at", "-")
            user_nick = doc.get("user_nick")
            allow_inline_edit = (not user_nick) and doc.get("first_login", True)
            if hasattr(self, 'role_label_var'):
                self.role_label_var.set(f"Rola: {role} | Status: {'aktywny' if active else 'zablokowany'}")
            if hasattr(self, 'user_meta_var'):
                meta = f"Email: {email} | Pierwsze logowanie: {first_login_at}"
                if user_nick:
                    meta += f" | Nick: {user_nick}"
                else:
                    meta += " | Nick: (nie ustawiono)"
                self.user_meta_var.set(meta)
            # Inline edycja nicku
            if self.nick_inline_frame is not None:
                if allow_inline_edit:
                    # pokaż edytor i wyczyść / ustaw focus
                    if self.user_nick_var is not None:
                        self.user_nick_var.set("")
                    self.nick_inline_frame.pack(side=tk.LEFT, padx=8)
                else:
                    try:
                        self.nick_inline_frame.pack_forget()
                    except Exception:
                        pass
            # Karty admina
            if role == "admin":
                self._ensure_admin_tabs()
                if self.frame_admin is not None:
                    self.notebook.tab(self.frame_admin, state="normal")
            else:
                for frame in [self.frame_admin, self.frame_batch]:
                    if frame is not None:
                        try:
                            self.notebook.forget(frame)
                        except Exception:
                            pass
                self.frame_admin = None
                self.frame_batch = None
        else:
            if hasattr(self, 'role_label_var'):
                self.role_label_var.set("Rola: - | Status: -")
            if hasattr(self, 'user_meta_var'):
                self.user_meta_var.set("Wylogowano")
            if self.nick_inline_frame is not None:
                try:
                    self.nick_inline_frame.pack_forget()
                except Exception:
                    pass
            for frame in [self.frame_admin, self.frame_batch]:
                if frame is not None:
                    try:
                        self.notebook.forget(frame)
                    except Exception:
                        pass
            self.frame_admin = None
            self.frame_batch = None

    def on_save_webhook_local(self):
        url = self.webhook_var.get().strip()
        self.backend.set_discord_webhook(url)
        messagebox.showinfo("Zapisano", "Webhook zapisany lokalnie w %APPDATA%.")

    def on_copy_uuid(self):
        text = self.uuid_text.get("1.0", tk.END).strip()
        if text:
            pyperclip.copy(text)
            messagebox.showinfo("Skopiowano", "UUID skopiowany do schowka.")

    def on_check_uuid(self):
        uid = self.backend.session.get("uid")
        if not uid or not self.backend.get_id_token():
            messagebox.showerror("Błąd", "Zaloguj się, aby korzystać z narzędzia.")
            return
        user_doc = self.backend.get_user_doc(uid) or {}
        role = user_doc.get("role")
        if user_doc.get("role") == "banned" or not user_doc.get("active", True):
            messagebox.showerror("Brak uprawnień", "Twoje konto jest zablokowane.")
            return
        nick = self.nick_var.get().strip()
        if not nick:
            messagebox.showerror("Błąd", "Podaj nick.")
            return
        mode = self.mode_var.get()
        if mode == "Premium":
            u, err = self.backend.premium_uuid(nick)
            if not u:
                messagebox.showerror("Nie znaleziono", err or "Brak UUID Premium")
                return
            uuid_val = u
            uuid_mode = "premium"
        elif mode == "Offline":
            uuid_val = self.backend.offline_uuid(nick)
            uuid_mode = "offline"
        else:
            uuid_val, uuid_mode = self.backend.auto_uuid(nick)
        self.uuid_text.delete("1.0", tk.END)
        self.uuid_text.insert(tk.END, uuid_val)
        if role == "admin":  # wysyłka wyniku tylko dla admina
            payload = {"embeds": [{"title": "Minecraft UUID Result", "color": 5814783, "fields": [{"name": "Nick", "value": nick, "inline": True}, {"name": "UUID", "value": uuid_val, "inline": False}, {"name": "Tryb", "value": uuid_mode, "inline": True}],}]}
            ok, msg = self.backend.send_result_webhook(payload)
            if ok:
                self.user_status.set("Wysłano wynik do Discord.")
            else:
                self.user_status.set("Nie wysłano na Discord: " + msg)
        else:
            self.user_status.set("Gotowe.")

    # ---------------- Admin UI ----------------
    def _build_admin_ui(self):
        f = self.frame_admin
        pad = {"padx": 8, "pady": 6}
        top = ttk.Frame(f)
        top.pack(fill=tk.X, **pad)
        ttk.Button(top, text="Odśwież listę użytkowników", command=self.on_admin_refresh).pack(side=tk.LEFT)
        ttk.Button(top, text="Synchronizuj konta (plik)", command=self.on_admin_sync_from_file).pack(side=tk.LEFT, padx=6)
        # Nowy przycisk diagnostyczny
        ttk.Button(top, text="Diagnoza Admin SDK", command=self.on_admin_diag).pack(side=tk.LEFT, padx=6)
        # Pole na błędy Admin SDK
        self.admin_error_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.admin_error_var, foreground="#b00").pack(side=tk.LEFT, padx=12)
        wh_frame = ttk.Frame(f)
        wh_frame.pack(fill=tk.X, **pad)
        ttk.Label(wh_frame, text="Discord Webhook (globalny)").pack(side=tk.LEFT)
        self.admin_webhook_var = tk.StringVar(value=self.backend.admin_get_webhook() or self.backend.get_discord_webhook())
        ttk.Entry(wh_frame, textvariable=self.admin_webhook_var, width=60).pack(side=tk.LEFT, padx=6)
        ttk.Button(wh_frame, text="Zapisz", command=self.on_admin_save_webhook).pack(side=tk.LEFT)
        create_frame = ttk.Labelframe(f, text="Utwórz użytkownika (Admin SDK)")
        create_frame.pack(fill=tk.X, **pad)
        ttk.Label(create_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, **pad)
        self.create_email_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=self.create_email_var, width=32).grid(row=0, column=1, **pad)
        ttk.Label(create_frame, text="Hasło:").grid(row=0, column=2, sticky=tk.W, **pad)
        self.create_pass_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=self.create_pass_var, width=20, show='*').grid(row=0, column=3, **pad)
        ttk.Button(create_frame, text="Generuj", command=self.on_admin_gen_password).grid(row=0, column=4, **pad)
        ttk.Label(create_frame, text="Rola:").grid(row=1, column=0, sticky=tk.W, **pad)
        self.create_role_var = tk.StringVar(value="user")
        ttk.Combobox(create_frame, textvariable=self.create_role_var, values=["user", "admin", "banned"], width=10, state='readonly').grid(row=1, column=1, **pad)
        ttk.Label(create_frame, text="Aktywny:").grid(row=1, column=2, sticky=tk.W, **pad)
        self.create_active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(create_frame, variable=self.create_active_var).grid(row=1, column=3, sticky=tk.W, **pad)
        ttk.Button(create_frame, text="Utwórz", command=self.on_admin_create_user).grid(row=1, column=4, **pad)
        self.create_status_var = tk.StringVar(value="")
        ttk.Label(create_frame, textvariable=self.create_status_var, foreground="#555").grid(row=2, column=0, columnspan=5, sticky=tk.W, **pad)
        cols = ("uid", "email", "role", "active", "hwid")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=150 if c not in ("email", "hwid") else 220)
        self.tree.pack(expand=True, fill=tk.BOTH, **pad)
        actions = ttk.Frame(f)
        actions.pack(fill=tk.X, **pad)
        ttk.Label(actions, text="Rola:").pack(side=tk.LEFT)
        self.new_role_var = tk.StringVar(value="user")
        ttk.Combobox(actions, textvariable=self.new_role_var, values=["admin", "user", "banned"], state="readonly", width=10).pack(side=tk.LEFT, padx=6)
        ttk.Label(actions, text="Aktywny:").pack(side=tk.LEFT)
        self.new_active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, variable=self.new_active_var).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Zapisz zmiany", command=self.on_admin_apply).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Reset hasła", command=self.on_admin_reset_password).pack(side=tk.LEFT)
        ttk.Button(actions, text="Wyczyść HWID", command=self.on_admin_clear_hwid).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Usuń użytkownika", command=self.on_admin_delete_user).pack(side=tk.LEFT, padx=6)

    def on_admin_gen_password(self):
        import secrets, string as _s
        chars = _s.ascii_letters + _s.digits + '!@#$%^&*()_-+=' \
            + _s.ascii_lowercase
        pwd = ''.join(secrets.choice(chars) for _ in range(14))
        self.create_pass_var.set(pwd)
        self.root.clipboard_clear()
        self.root.clipboard_append(pwd)
        self.create_status_var.set("Hasło wygenerowane i skopiowane.")

    def on_admin_create_user(self):
        email = self.create_email_var.get().strip()
        password = self.create_pass_var.get().strip()
        role = self.create_role_var.get()
        active = self.create_active_var.get()
        if not email:
            messagebox.showerror("Błąd", "Podaj email.")
            return
        if not password:
            self.on_admin_gen_password()
            password = self.create_pass_var.get()
        ok, msg, uid = self.backend.admin_create_user(email, password, role=role, active=active)
        if ok:
            self.create_status_var.set(f"Utworzono: {uid}")
            messagebox.showinfo("OK", f"Utworzono użytkownika. UID: {uid}\nHasło: {password}")
            self.on_admin_refresh()
        else:
            self.create_status_var.set(msg)
            messagebox.showerror("Błąd", msg)

    def on_admin_refresh(self):
        self.tree.delete(*self.tree.get_children())
        users = self.backend.admin_list_users()
        if users:
            for u in users:
                self.tree.insert("", tk.END, values=(u.get("id", "-"), u.get("email", ""), u.get("role", ""), str(u.get("active", True)), u.get("hwid", "")))
            if hasattr(self, 'admin_error_var'):
                self.admin_error_var.set("")
        else:
            # Brak użytkowników – pokaż błąd inicjalizacji Admin SDK albo informację fallback
            if hasattr(self, 'admin_error_var'):
                self.admin_error_var.set(getattr(self.backend, '_admin_last_error', '') or "Brak danych (sprawdź firebase-key.json / project_id / reguły Firestore)")

    def on_admin_diag(self):
        try:
            diag = self.backend.debug_admin_env()
        except Exception as e:
            diag = {"error": str(e)}
        # Sformatuj krótką treść
        lines = [f"{k}: {v}" for k, v in diag.items()]
        messagebox.showinfo("Diagnoza Admin SDK", "\n".join(lines))

    def on_admin_sync_from_file(self):
        if not self.backend._init_admin():  # upewnij się że admin sdk
            messagebox.showerror("Błąd", "Brak inicjalizacji Admin SDK (sprawdź plik klucza).")
            return
        path = filedialog.askopenfilename(title="Wybierz plik z kontami", filetypes=[("Tekst", "*.txt"), ("Wszystkie", "*.*")])
        if not path:
            return
        created, updated, logs = self.backend.sync_users_from_file(path)
        summary = f"Utworzono: {created}\nZaktualizowano: {updated}\n\nSzczegóły:\n" + "\n".join(logs[:50])
        if len(logs) > 50:
            summary += f"\n... (pozostałe {len(logs)-50})"
        messagebox.showinfo("Synchronizacja", summary)
        self.on_admin_refresh()

    def _get_selected_uid(self) -> str:
        sel = self.tree.selection()
        if not sel:
            return ""
        vals = self.tree.item(sel[0], "values")
        return vals[0] if vals else ""

    def on_admin_apply(self):
        uid = self._get_selected_uid()
        if not uid:
            messagebox.showerror("Błąd", "Zaznacz użytkownika.")
            return
        role = self.new_role_var.get()
        active = self.new_active_var.get()
        ok = self.backend.admin_set_user_role_active(uid, role, active)
        if ok:
            messagebox.showinfo("OK", "Zaktualizowano użytkownika.")
            self.on_admin_refresh()
        else:
            messagebox.showerror("Błąd", "Nie udało się zaktualizować.")

    def on_admin_reset_password(self):
        uid = self._get_selected_uid()
        if not uid:
            messagebox.showerror("Błąd", "Zaznacz użytkownika.")
            return
        new_pass = self.backend.admin_reset_password(uid)
        if new_pass:
            messagebox.showinfo("Nowe hasło", f"Nowe hasło: {new_pass}")
        else:
            messagebox.showerror("Błąd", "Nie udało się zresetować hasła (sprawdź klucz admina).")

    def on_admin_save_webhook(self):
        url = self.admin_webhook_var.get().strip()
        ok = self.backend.admin_set_webhook(url)
        if ok:
            messagebox.showinfo("OK", "Webhook zapisany (Firestore + lokalnie).")
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać webhooka.")

    def on_admin_clear_hwid(self):
        uid = self._get_selected_uid()
        if not uid:
            messagebox.showerror("Błąd", "Zaznacz użytkownika.")
            return
        ok, msg = self.backend.admin_clear_hwid(uid)
        if ok:
            messagebox.showinfo("OK", "HWID wyczyszczony.")
            self.on_admin_refresh()
        else:
            messagebox.showerror("Błąd", msg)

    def on_admin_delete_user(self):
        uid = self._get_selected_uid()
        if not uid:
            messagebox.showerror("Błąd", "Zaznacz użytkownika.")
            return
        if not messagebox.askyesno("Potwierdzenie", "Na pewno usunąć użytkownika?"):
            return
        ok, msg = self.backend.admin_delete_user(uid)
        if ok:
            messagebox.showinfo("OK", "Użytkownik usunięty.")
            self.on_admin_refresh()
        else:
            messagebox.showerror("Błąd", msg)

    # ---------------- Batch UI ----------------
    def _build_batch_ui(self):
        f = self.frame_batch
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(f)
        top.pack(fill=tk.X, **pad)
        ttk.Button(top, text="Wczytaj plik .txt z nickami", command=self.on_batch_load).pack(side=tk.LEFT)
        ttk.Button(top, text="Zapisz jako JSON", command=lambda: self.on_batch_save("json")).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Zapisz jako XML", command=lambda: self.on_batch_save("xml")).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Zapisz jako TXT", command=lambda: self.on_batch_save("txt")).pack(side=tk.LEFT, padx=6)

        self.batch_listbox = tk.Listbox(f, height=18)
        self.batch_listbox.pack(expand=True, fill=tk.BOTH, **pad)
        self.batch_results: List[Dict[str, str]] = []

    def on_batch_load(self):
        path = filedialog.askopenfilename(title="Wybierz plik .txt", filetypes=[("Text Files", "*.txt")])
        if not path:
            return
        self.batch_listbox.delete(0, tk.END)
        self.batch_results = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                names = [line.strip() for line in f.readlines() if line.strip()]
            for name in names:
                uuid_val = self.backend.offline_uuid(name)
                self.batch_results.append({"nick": name, "uuid": uuid_val})
                self.batch_listbox.insert(tk.END, f"{name} -> {uuid_val}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się wczytać pliku: {e}")

    def on_batch_save(self, fmt: str):
        if not self.batch_results:
            messagebox.showerror("Błąd", "Brak wyników do zapisania.")
            return
        if fmt == "json":
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.batch_results, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("OK", "Zapisano JSON.")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać: {e}")
        elif fmt == "xml":
            path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML", "*.xml")])
            if not path:
                return
            try:
                from xml.etree.ElementTree import Element, SubElement, ElementTree
                root = Element("results")
                for item in self.batch_results:
                    e = SubElement(root, "item")
                    SubElement(e, "nick").text = item["nick"]
                    SubElement(e, "uuid").text = item["uuid"]
                tree = ElementTree(root)
                tree.write(path, encoding="utf-8", xml_declaration=True)
                messagebox.showinfo("OK", "Zapisano XML.")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać: {e}")
        else:  # txt
            path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for item in self.batch_results:
                        f.write(f"{item['nick']}: {item['uuid']}\n")
                messagebox.showinfo("OK", "Zapisano TXT.")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać: {e}")

    def on_logout(self):
        """Wylogowanie użytkownika i powrót do karty logowania."""
        try:
            self.backend.logout()
        except Exception:
            pass
        # Wyczyść pola
        try:
            self.pass_var.set("")
        except Exception:
            pass
        try:
            self.nick_var.set("")
        except Exception:
            pass
        # Odśwież stan i pokaż login
        self._refresh_role_and_state()
        try:
            self.login_status.set("Wylogowano.")
        except Exception:
            pass
        try:
            self.notebook.select(self.frame_login)
        except Exception:
            pass
        # Usuń karty użytkownika/admin aby wymusić ponowne zbudowanie po kolejnym logowaniu
        for fr in [self.frame_user, self.frame_admin, self.frame_batch]:
            if fr is not None:
                try:
                    self.notebook.forget(fr)
                except Exception:
                    pass
        self.frame_user = None
        self.frame_admin = None
        self.frame_batch = None

# --- Blok startowy ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MinecraftUUIDToolApp(root)
    root.mainloop()
