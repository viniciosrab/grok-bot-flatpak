# Unofficial Grok Bot Flatpak

Grok Bot packaged as a Flatpak (`io.github.viniciosrab.GrokBot`) for Linux on `x86_64` and `aarch64`. Install and update it from this repository's Pages Flatpak repository.

> [!IMPORTANT]
> This is an **unofficial, community-maintained package**. It is not endorsed, published, or supported by the Grok Bot vendor.

## Install

Install Flatpak through your Linux distribution, then run:

```bash
flatpak remote-add --user --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo

flatpak remote-add --user --if-not-exists grok-bot \
  https://viniciosrab.github.io/grok-bot-flatpak/grok-bot.flatpakrepo

flatpak install --user grok-bot \
  io.github.viniciosrab.GrokBot//master
```

Flathub is only used for the KDE runtime below. The application itself is not available on Flathub.

If you already added this remote before signature verification was published, delete it and run the commands above again:

```bash
flatpak remote-delete --user grok-bot
```

## Launch

Launch Grok Bot from your desktop application menu or run:

```bash
flatpak run io.github.viniciosrab.GrokBot
```

## Update

The bundled updater is disabled. Update only through Flatpak:

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

## Compatibility

| Topic | Expectation |
|-------|-------------|
| Architectures | `x86_64` and `aarch64` |
| Sessions | Wayland and X11 |
| Tray integration | Follows the KDE StatusNotifier standard; fullest experience on KDE Plasma |
| Runtime | KDE Platform 6.11, fetched from Flathub |
| Link handling | `grokbot:` and `sand:` links open in the application |

## Limitations and trust

- Unofficial package; for vendor support, use the vendor's own distribution.
- Grok Bot itself remains proprietary upstream software.
- Flatpak verifies this repository's signature. That authenticates the package build, not the upstream vendor.

## Releases and downloads

Public releases are titled `Grok Bot vVERSION`, one per upstream version. Install and update from the [Flatpak repository](https://viniciosrab.github.io/grok-bot-flatpak/). The `site.tar.gz` files attached to [GitHub Releases](https://github.com/viniciosrab/grok-bot-flatpak/releases) are publication audit artifacts, not application installers.

## Report issues

Report packaging problems at [GitHub Issues](https://github.com/viniciosrab/grok-bot-flatpak/issues).

## Contributing

Want to help with packaging or automation? See [CONTRIBUTING.md](CONTRIBUTING.md).
