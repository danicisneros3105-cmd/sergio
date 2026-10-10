# Sergio on your phone

```bash
sergio movil            # secure tunnel + QR code
sergio movil --sin-tunel   # same Wi-Fi only, no tunnel
sergio movil estado
sergio movil olvidar    # unpair every phone
```

`sergio movil` opens a Cloudflare quick tunnel (HTTPS, no account needed) to
the Sergio server on this computer and prints a QR code. Scanning it opens
Sergio on the phone, already paired. Choose **Add to Home Screen** to install
it like an app (it is a PWA with shortcuts to Chat, Cowork and Deep thinking).

- Only requests carrying the phone's pairing token get past the tunnel. The
  token arrives in the QR link's fragment, which browsers never send to
  servers, and is then kept on the phone.
- The tunnel lives while the command runs; Ctrl+C closes it.
- Your computer has to be on, with Sergio's server running: the phone is a
  window onto it, and nothing is stored on third-party servers.

## Offline

Without a connection the app still opens. Past conversations are on the phone,
and the last 200 answers are kept in the browser's IndexedDB: asking the same
question again shows the saved answer with its date. New questions wait in the
box until the connection is back.
