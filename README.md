# Unofficial Grok Bot Flatpak

Install Grok Bot on Linux through the independently maintained Flatpak Repository for `io.github.viniciosrab.GrokBot`.

> [!IMPORTANT]
> This is an **Unofficial Flatpak**. It is not endorsed, published, or supported by the Grok Bot vendor.

## Install

Install Flatpak through your Linux distribution, then run:

```bash
flatpak remote-add --user --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo

flatpak remote-add --user --if-not-exists --no-gpg-verify grok-bot \
  https://viniciosrab.github.io/grok-bot-flatpak/

flatpak install --user grok-bot \
  io.github.viniciosrab.GrokBot//master
```

The Flatpak Repository currently publishes `x86_64` and `aarch64` builds.

### Signature limitation

The repository is signed during publication, but its public signing key and a `.flatpakrepo` configuration file are not published yet. The `--no-gpg-verify` option is therefore currently required when adding the remote. HTTPS still protects the repository in transit, but it does not replace client-side signature verification.

## Run

Launch Grok Bot from your desktop application menu or run:

```bash
flatpak run io.github.viniciosrab.GrokBot
```

## Update

```bash
flatpak update --user io.github.viniciosrab.GrokBot
```

## Uninstall

Remove the application and its local Flatpak data:

```bash
flatpak uninstall --user --delete-data io.github.viniciosrab.GrokBot
```

Remove the repository as well if you no longer need it:

```bash
flatpak remote-delete --user grok-bot
```

## Release model

Each Stable Upstream Release is accepted only when every supported architecture has a verified Upstream Artifact and Source Checksum. Reproducible integration changes produce the Packaged Payload, which is validated on both architectures before publication as one Atomic Flatpak Release.

Users install and receive updates from the [Flatpak Repository](https://viniciosrab.github.io/grok-bot-flatpak/). The `site.tar.gz` files attached to [GitHub Releases](https://github.com/viniciosrab/grok-bot-flatpak/releases) are publication audit and rollback artifacts, not application installers.

The Packaged Payload uses the Official Grok Bot Icon without redesigning or recreating it.

## Project verification

The repository contains automated checks for source pins, payload integration, both supported architectures, and the KDE tray runtime boundary. Run the local workspace gate with:

```bash
python3 tools/test.py
```

Architecture decisions and provenance rules are documented in [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/).
