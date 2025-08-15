# Minecraft UUID Tool (Tkinter + Firebase)

Aplikacja desktopowa (Python/Tkinter) do wyszukiwania UUID Minecraft z integracją Firebase Authentication i Firestore.

Funkcje:
- Logowanie/Rejestracja (email + hasło) z auto-logowaniem dzięki refresh_token (Identity Toolkit REST API).
- Panel użytkownika: sprawdzanie UUID w trybach Auto/Premium/Offline, kopiowanie UUID, wysyłka na Discord Webhook.
- Panel administratora: lista użytkowników (Firestore), zmiana roli/aktywności, reset hasła (Firebase Admin SDK), edycja webhooka (meta/webhooks).
- Zakładka Batch Offline: wczytanie listy nicków i zapis wyników do JSON/XML/TXT.
- HWID zapisywany przy pierwszym logowaniu.
- Webhook i sesja zapisywane w %APPDATA%/MinecraftUUIDTool/config.json.

## Struktura projektu

- `minecraft_uuid_tool.py` – główny kod GUI (Tkinter)
- `firebase_backend.py` – logika Firebase (Auth REST, Firestore REST, Admin SDK)
- `config.json` – konfiguracja projektu (Web API Key, Project ID, ścieżka do klucza serwisowego)
- `firebase-key.json` – klucz serwisowy (przykład formatu; wstaw własny plik pobrany z Firebase Console)
- `firestore.rules` – reguły bezpieczeństwa Firestore
- `requirements.txt` – zależności

## Wymagania wstępne
- Python 3.9+
- Konto Firebase z włączonym Authentication (Email/Password) i Firestore (tryb produkcyjny)
- Web API Key (z ustawień projektu) i Service Account JSON do Admin SDK

## Instalacja zależności

Windows (PowerShell):

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Konfiguracja

1. Uzupełnij `config.json`:
   - `project_id`: ID projektu Firebase
   - `web_api_key`: Web API Key (z ustawień projektu)
   - `service_account_file`: ścieżka do pliku klucza serwisowego (np. `firebase-key.json`)

2. Skopiuj plik klucza serwisowego (Service Account) do pliku `firebase-key.json` w katalogu projektu lub do `%APPDATA%\MinecraftUUIDTool\firebase-key.json`.

3. Ustaw reguły Firestore – w Firebase Console lub CLI wgraj zawartość `firestore.rules`.

### Struktura danych Firestore

- `users/{uid}` – dokument użytkownika
  - `email: string`
  - `role: string` – `admin|user|banned`
  - `active: boolean`
  - `hwid: string`
  - `first_login: boolean`

- `meta/admins/list` – dokument z listą UID adminów
  - `uids: array<string>`

- `meta/webhooks` – dokument z webhookiem Discord
  - `discord: string`

Aby dodać pierwszego admina: dodaj UID do tablicy `uids` w `meta/admins/list`. Aplikacja przy logowaniu ustawi mu rolę `admin` w `users/{uid}`.

## Reguły Firestore (skrót)

Zawarte w pliku `firestore.rules`. Logika:
- Tylko zalogowani czytają własny dokument; admin może wszystko w `users/*`.
- Zwykli użytkownicy nie mogą edytować cudzych dokumentów.
- `meta/*` dostępne tylko dla admina.

## Uruchomienie aplikacji

```powershell
python minecraft_uuid_tool.py
```

Po pierwszym uruchomieniu aplikacja utworzy katalog `%APPDATA%\MinecraftUUIDTool` i zapisze tam konfigurację użytkownika (w tym sesję i webhook).

## Budowa pliku .exe (PyInstaller)

Zainstaluj PyInstaller i zbuduj:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name "MinecraftUUIDTool" minecraft_uuid_tool.py
```

Artefakt znajdziesz w `dist/MinecraftUUIDTool.exe`.

## Uwagi bezpieczeństwa
- Nie commituj prawdziwego `firebase-key.json`. Przechowuj go lokalnie.
- Admin SDK w aplikacji desktopowej umożliwia operacje admina – zabezpiecz dystrybucję i klucz.
- Dzięki zastosowaniu REST + idToken zwykłe operacje użytkownika podlegają regułom Firestore.

## Rozwiązywanie problemów
- Błąd logowania: sprawdź poprawność Web API Key, włączony provider Email/Password.
- Operacje admina nie działają: upewnij się, że `firebase-key.json` istnieje i odpowiada projektowi.
- Brak uprawnień: sprawdź pole `role` oraz `active` w dokumencie `users/{uid}`.
