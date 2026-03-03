# RGPy (core)

Ce dossier contient un portage Python de la logique principale de Ratio Ghost:
- chargement/sauvegarde des settings
- proxy HTTP local
- proxy UDP local (BEP 15 `connect`/`announce`)
- re-ecriture des announces tracker (`downloaded`, `uploaded`, `left`)
- aggregation des statistiques

## Lancement

```bash
python -m rgpy.app
```

Optionnel:

```bash
python -m rgpy.app --port 3773
```

## Lancement WebUI

```bash
python -m rgpy.webui --port 3773 --webui-port 8088 --verbose
```

Puis ouvrir:

```text
http://127.0.0.1:8088
```

## Build Executables (PyInstaller)

Depuis la racine du repo:

```bash
python -m pip install pyinstaller
python scripts/build_binaries.py
```

Sortie:
- `dist/rgpy-cli(.exe)`
- `dist/rgpy-webui(.exe)`

Lanceurs sources utilises:
- `rgpy_cli.py`
- `rgpy_webui.py`

## Telechargement sans sources (GitHub Actions)

Le workflow `.github/workflows/build-binaries.yml` produit des artefacts telechargeables:
- `rgpy-windows-latest`
- `rgpy-ubuntu-latest`
- `rgpy-macos-latest`

Usage:
1. pousser le repo sur GitHub
2. ouvrir l'onglet `Actions` -> `Build Binaries`
3. lancer `Run workflow`
4. telecharger les artefacts (binaires only)

La WebUI permet de:
- voir les stats en direct
- voir un journal `events` (style ancien Ratio Ghost)
- modifier les settings principaux
- sauvegarder les settings dans `settings.json`
- redemarrer le programme via le bouton `Recharger (redemarrer)`

Note: certains changements structurels (ex: `listen_port`, `udp_enabled`) necessitent un redemarrage du process pour s'appliquer.

## Mode MITM HTTPS

Le mode MITM HTTPS est desactive par defaut (`mitm_https=0`).

Pour l'activer:
- cocher `MITM HTTPS` dans la WebUI
- verifier `mitm_cert_path` et `mitm_key_path` (par defaut: `tls/server.crt` et `tls/server.key`)
- cliquer `Recharger (redemarrer)`

Important:
- pour que le client accepte l'interception HTTPS, le certificat local doit etre installe comme certificat de confiance (OS/client BitTorrent).
- `mitm_insecure_upstream=1` desactive la verification TLS vers le tracker distant (plus permissif). Utilisez `0` si vous voulez verifier le certificat upstream.

## Configuration UDP (BEP 15)

Le support UDP est active par `udp_enabled=1`.

Le routage UDP multi-trackers est automatique quand le client envoie des datagrammes SOCKS5 UDP (destination incluse dans le paquet).

En fallback, le proxy reutilise le mapping BEP 15 `connection_id -> tracker` par client.

En dernier recours, vous pouvez definir un upstream statique:
- `udp_upstream_host`: hostname/IP du tracker UDP distant
- `udp_upstream_port`: port UDP du tracker distant

Ces valeurs sont stockees dans `settings.json` et servent de secours.

Pour limiter le bruit des logs HTTPS tunnel en mode `--verbose`, laissez `log_tunnel_chunks=0` (defaut).
Mettez `log_tunnel_chunks=1` seulement pour du debug bas niveau TCP.

## Limites du portage

- L'interface GUI Tcl/Tk n'est pas reproduite ici.
- Le flux TLS MITM historique n'est pas reproduit a l'identique.
- Sans en-tete SOCKS5 UDP et sans mapping `connection_id`, il faut un upstream statique (`udp_upstream_host`/`udp_upstream_port`).
- Le comportement reste axe sur la logique proxy/tracker et les statistiques.
