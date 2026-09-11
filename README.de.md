# dyndns-hcloud

[English](README.md) | Deutsch

Damit deine Domain auch bei wechselnder Internetadresse auf dein Heimnetz zeigt.
Dieser Python-Dienst empfängt Aktualisierungen von einer FRITZ!Box und aktualisiert
deine DNS-Einträge bei Hetzner. Außerdem kann er Geräten wie einem NAS eine eigene
IPv6-Subdomain zuweisen.

## Erste Schritte

Diese Installationsanleitung richtet sich an neuere Versionen von **Ubuntu** und
**Raspberry Pi OS** (Lite oder Desktop) mit Python 3.11 oder neuer.
Du benötigst eine DNS-Zone in der Hetzner Console und einen API-Token mit Lese- und
Schreibrechten für das zugehörige Projekt. Der Dienst muss von deiner FRITZ!Box aus
erreichbar sein. Du kannst ihn auf einem Raspberry Pi in deinem vertrauenswürdigen
Heimnetz direkt über HTTP betreiben, ohne Reverse Proxy. Für Verbindungen über das
Internet solltest du [HTTPS](#https-einrichten) verwenden.

### 1. Voraussetzungen installieren

Die Schritte sind auf beiden Systemen gleich. Installiere Python und die benötigten
Systempakete:

```sh
sudo apt update
sudo apt install python3 python3-venv ca-certificates
```

### 2. Anwendung installieren

Lade dieses Repository herunter oder klone es und führe anschließend diese Befehle
in seinem Verzeichnis aus:

```sh
sudo install -d -m 755 /opt/dyndns-hcloud
sudo /usr/bin/python3 -m venv /opt/dyndns-hcloud/venv
sudo /opt/dyndns-hcloud/venv/bin/python -m pip install .
```

Der Befehl `venv` erstellt unter `/opt/dyndns-hcloud` eine separate Umgebung für die
Bibliotheken dieses Dienstes; sie verwendet weiterhin diesen Python-Interpreter.
`pip install .` installiert dort die Anwendung aus dem aktuellen Verzeichnis (`.`)
und ihre Abhängigkeiten. Du musst in deiner Shell nichts aktivieren; systemd
verwendet automatisch den vollständigen Pfad.

Dies folgt den Empfehlungen zur Python-Installation von
[Ubuntu](https://ubuntu.com/developers/docs/tutorials/python-use/) und
[Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html#use-python-on-a-raspberry-pi).
Dabei bleiben per pip installierte Bibliotheken von den Python-Paketen getrennt,
die das Betriebssystem verwaltet.

### 3. Konfigurationsdatei erstellen

Kopiere die Beispielkonfiguration aus dem Repository-Verzeichnis:

```sh
sudo mkdir -p /etc/dyndns-hcloud
sudo cp --update=none config.example.toml /etc/dyndns-hcloud/config.toml
sudo chown root:root /etc/dyndns-hcloud/config.toml
sudo chmod 600 /etc/dyndns-hcloud/config.toml
```

Die Konfiguration liegt unter `/etc/dyndns-hcloud/config.toml`. Der Kopierbefehl
lässt eine vorhandene Konfiguration unverändert, und die Dateirechte 600 schützen
die enthaltenen Zugangsdaten.

Bearbeite die Konfiguration mit:

```sh
sudoedit /etc/dyndns-hcloud/config.toml
```

Trage deine Domain, deinen Hetzner-API-Token sowie einen separaten Benutzernamen und
ein Passwort für DynDNS ein. Verwende für die DynDNS-Zugangsdaten Buchstaben,
Ziffern, `-` und `_`, damit sie in der Update-URL funktionieren. Der Hetzner-Token
bleibt auf dem Rechner, auf dem der Dienst läuft.

Standardmäßig zeigt deine Domain (zum Beispiel `example.com`) auf die IPv4- und
IPv6-Adressen des Routers. Um einem Gerät eine eigene Subdomain zu geben, passe die
Beispiele unter `[[records]]` mit seinem Namen und seiner Ethernet-MAC-Adresse an.
Entferne diese Einträge, wenn du nur die Hauptdomain (`example.com`) aktualisieren
möchtest.

Die IPv6-Adressen der Geräte werden aus dem LAN-Präfix und der MAC-Adresse
berechnet. Das Gerät muss eine passende EUI-64-Adresse verwenden; siehe
[IPv6-Adressen der Clients](#ipv6-adressen-der-clients).

### 4. Dienst starten

Die Standardkonfiguration lauscht auf allen IPv4- und IPv6-Schnittstellen:

```toml
host = "*"
```

Du kannst stattdessen eine bestimmte IPv4- oder IPv6-Adresse im LAN angeben, um nur
dort zu lauschen. Für einen Reverse Proxy auf demselben Rechner verwendest du
`127.0.0.1`, damit nur lokale IPv4-Verbindungen angenommen werden.

```sh
sudo /opt/dyndns-hcloud/venv/bin/python -m dyndns_hcloud --config /etc/dyndns-hcloud/config.toml --check-config
sudo cp deploy/dyndns-hcloud.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dyndns-hcloud
sudo systemctl status dyndns-hcloud
```

Führe diese Befehle im Repository-Verzeichnis aus. Der Dienst startet sofort und
bei jedem Systemstart automatisch unter einem eigenen Dienstkonto. Mit dem
Standardport ist er unter `http://192.168.178.20:8080` erreichbar, sofern dies die
LAN-IP deines Servers ist. Führe nach Konfigurationsänderungen
`sudo systemctl restart dyndns-hcloud` aus.

### 5. FRITZ!Box konfigurieren

Öffne **Internet → Freigaben → DynDNS** und fülle das Formular von oben nach unten
aus:

1. **DynDNS aktiv:** Aktiviere DynDNS. Falls deine FRITZ!OS-Version eine
   Anbieterauswahl anzeigt, wähle einen benutzerdefinierten Anbieter.
2. **Update-URL:** Füge die folgende URL als eine Zeile ein. Ersetze
   `192.168.178.20` durch die numerische LAN-IPv4-Adresse des Rechners, auf dem der
   Dienst läuft, und verwende den konfigurierten Port. Lass die Platzhalter
   einschließlich der spitzen Klammern unverändert:

   ```text
   http://192.168.178.20:8080/update?username=<username>&password=<pass>&hostname=<domain>&ipaddr=<ipaddr>&ip6addr=<ip6addr>&ip6lanprefix=<ip6lanprefix>
   ```

3. **Domainnamen:** Trage die Domain ein, die du unter `[hetzner]` als `zone` in
   `/etc/dyndns-hcloud/config.toml` festgelegt hast, zum Beispiel `example.com`.
4. **Benutzername:** Trage den Wert von `username` ein, den du unter `[server]` in
   `/etc/dyndns-hcloud/config.toml` festgelegt hast.
5. **Kennwort:** Trage den Wert von `password` ein, den du unter `[server]` in
   `/etc/dyndns-hcloud/config.toml` festgelegt hast. Gib die Zugangsdaten ohne die
   TOML-Anführungszeichen ein.

Speichere die Einstellungen. Beim Senden einer Aktualisierung ersetzt die
FRITZ!Box die URL-Platzhalter durch die Werte dieser Felder und ihre aktuellen
Adressen.

Verwende beim Betrieb im lokalen Netz eine numerische LAN-Adresse: Ein lokaler
Hostname wie `home.fritz.box` kann auf deinem Computer funktionieren, aber im
DynDNS-Client der FRITZ!Box fehlschlagen. Reserviere die LAN-IP des Servers in der
FRITZ!Box, damit sie gleich bleibt.

HTTP überträgt die DynDNS-Zugangsdaten unverschlüsselt. Verwende diese Einrichtung
daher in einem vertrauenswürdigen LAN. Die ausgehenden Anfragen des Dienstes an
Hetzner verwenden weiterhin HTTPS.

Die FRITZ!Box kann nun Adressänderungen an den Dienst senden. DNS-Aktualisierungen
öffnen keine Firewall-Ports: Damit ein Gerät erreichbar ist, brauchst du außerdem
passende Firewall-Regeln auf dem Router und dem Gerät sowie Portfreigaben für IPv4.

## Erweiterte Einrichtung

### Konfigurationsoptionen

Eine Dienstkonfiguration verwaltet einen Router und eine vorhandene primäre
DNS-Zone. Die Zone muss an die autoritativen Nameserver von Hetzner delegiert sein.
Dieser Dienst verwendet die Cloud DNS API; ältere Zonen von `dns.hetzner.com`
müssen zuerst in die Hetzner Console migriert werden.

Ein vollständiges Beispiel findest du in [config.example.toml](config.example.toml).

Die **Hauptdomain** ist die Domain selbst, etwa `example.com`, ohne eine Subdomain
wie `nas`. Ihre Einstellungen stehen unter `[apex]` (der DNS-Fachbegriff dafür ist
„Zone Apex“). Standardmäßig wird `example.com` auf die aktuellen IPv4- und
IPv6-Adressen des Routers aufgelöst und bei jeder Aktualisierung durch die
FRITZ!Box angepasst. Mit `ipv4 = false` beziehungsweise `ipv6 = false` unter
`[apex]` lässt sich dies für die jeweilige Adressfamilie deaktivieren.

| Einstellung | Standardwert | Zweck |
| --- | --- | --- |
| `server.host` / `server.port` | `*` / `8080` | Auf allen IPv4- und IPv6-Schnittstellen lauschen |
| `hetzner.ttl` | `300` | DNS-Cache-Gültigkeitsdauer in Sekunden |
| `apex.ipv4` | `true` | `example.com` auf die aktuelle IPv4-Adresse des Routers setzen (A-Eintrag) |
| `apex.ipv6` | `true` | `example.com` auf die eigene aktuelle IPv6-Adresse des Routers setzen (AAAA-Eintrag) |
| `records[].ipv4` | `false` | Auch den A-Eintrag dieses Clients auf den Router setzen; für den Zugriff auf den Client über IPv4 eine Portfreigabe auf dem Router einrichten |
| `records[].subnet_id` | `0` | Ein LAN-/64-Netz innerhalb eines größeren IPv6-Präfixes auswählen |

Clientnamen sind relativ zur Zone: `nas` bedeutet `nas.example.com`, und
`home.server` bedeutet `home.server.example.com`. Jeder Client erhält einen aus
seiner MAC-Adresse abgeleiteten AAAA-Eintrag. Die Hauptdomain benötigt keine
MAC-Adresse. Um die Hauptdomain stattdessen einem Client anhand seiner MAC-Adresse
zuzuordnen, deaktiviere beide `[apex]`-Optionen und füge einen Client mit dem Namen
`@` hinzu.

**Der Dienst ersetzt jeden verwalteten A-/AAAA-Record-Satz durch eine einzelne
Adresse.** Verwende separate Namen, wenn du bereits Einträge mit mehreren Adressen
hast. Nicht verwaltete Namen und Eintragstypen bleiben unverändert. Wenn du eine
Option deaktivierst oder einen Client entfernst, bleiben dessen vorhandene
DNS-Einträge bestehen. Bei CNAME-Konflikten schlägt die Aktualisierungsanfrage fehl,
bevor Änderungen geschrieben werden.

Prüfe die Konfiguration, ohne den Server zu starten oder API-Anfragen zu senden:

```sh
sudo /opt/dyndns-hcloud/venv/bin/python -m dyndns_hcloud --config /etc/dyndns-hcloud/config.toml --check-config
```

Unbekannte Felder und ungültige Konfigurationswerte werden beim Start zurückgewiesen.

### IPv6-Adressen der Clients

Die eigene IPv6-Adresse des Routers (`<ip6addr>`) aktualisiert den AAAA-Eintrag der
Hauptdomain. Das LAN-Präfix (`<ip6lanprefix>`) wird ausschließlich zur Berechnung
der Clientadressen verwendet.

Beispielsweise ergeben das Präfix `2001:db8:1:2::/64` und die MAC-Adresse
`00:11:22:33:44:55` die Adresse `2001:db8:1:2:211:22ff:fe33:4455`. Dies verwendet
Modified EUI-64: `ff:fe` wird eingefügt und das Universal/Local-Bit der MAC-Adresse
umgekehrt. Prüfe, ob das Gerät diese Adresse tatsächlich hat. Privacy-Adressen,
stabile undurchsichtige Adressen (RFC 7217) und DHCPv6-Adressen lassen sich nicht
aus einer MAC-Adresse ableiten.

Eine Präfixadresse ohne Längenangabe wird als `/64` interpretiert. Ein explizit
angegebenes größeres Netz wie `2001:db8:1234:ab00::/56` wird ebenfalls akzeptiert:
`subnet_id = 42` wählt `2001:db8:1234:ab2a::/64` aus. Dies muss dem LAN entsprechen,
das dein Router bekannt gibt. Bei einer `/64`-Eingabe muss `subnet_id` null sein.
Präfixe mit gesetzten Host-Bits oder Präfixlängen größer als 64 werden zurückgewiesen.

Private IPv4-Adressen oder CGNAT-Adressen ermöglichen keine direkte öffentliche
Erreichbarkeit über IPv4.

### HTTPS einrichten

Beim Betrieb in einem vertrauenswürdigen LAN ist HTTPS optional. Für
Aktualisierungsanfragen über das Internet oder ein anderes nicht vertrauenswürdiges
Netz schaltest du einen HTTPS-Reverse-Proxy mit einem vertrauenswürdigen Zertifikat
vor den Dienst. Wenn der Proxy auf demselben Rechner läuft, verwende
`server.host = "127.0.0.1"` und mache nur den Proxy aus dem Internet erreichbar.

Verwende diese Update-URL mit der Domain deines Proxys:

```text
https://updates.example.net/update?username=<username>&password=<pass>&hostname=<domain>&ipaddr=<ipaddr>&ip6addr=<ip6addr>&ip6lanprefix=<ip6lanprefix>
```

Für Caddy kannst du [deploy/Caddyfile](deploy/Caddyfile) verwenden: Ersetze die
Beispieldomain und richte deren DNS auf den Rechner aus, auf dem der Dienst läuft.
Beim Hosting außerhalb deines Heimnetzes vermeidet ein Server mit stabiler
Verbindung, dass Aktualisierungen von der wechselnden Heimnetzadresse abhängen.
Für direkte lokale HTTP-Anfragen verwendest du die numerische LAN-Adresse.

Die URL der Aktualisierungsanfrage enthält Zugangsdaten. Deaktiviere die
Protokollierung von Query-Strings bei deinem Proxy und allen vorgeschalteten Proxys.
Das Caddy-Beispiel verzichtet auf Zugriffsprotokolle, und die Anwendung protokolliert
weder Anfrage-URLs noch Zugangsdaten. Clients, die HTTP Basic Authentication
unterstützen, können diese statt der Zugangsdaten in den URL-Parametern verwenden.

### Automatisch mit systemd ausführen

Die [systemd-Unit](deploy/dyndns-hcloud.service) führt die installierte Anwendung
mit `/opt/dyndns-hcloud/venv/bin/python` aus. Das Argument `-m dyndns_hcloud` weist
Python an, dieses Paket zu finden und auszuführen; das heruntergeladene Repository
wird im laufenden Betrieb nicht benötigt.

Die Unit liest `/etc/dyndns-hcloud/config.toml`, die in der Anleitung für die ersten
Schritte eingerichtet wurde. Sie verwendet `DynamicUser` und systemd-Credentials,
um dem Dienst eine private, lesbare Kopie bereitzustellen. Die Anwendung läuft ohne
Root-Rechte. Die Anleitung installiert und aktiviert die Unit; mit diesen Befehlen
kannst du sie verwalten:

```sh
sudo systemctl restart dyndns-hcloud
sudo systemctl stop dyndns-hcloud
sudo journalctl -u dyndns-hcloud -f
```

Betreibe pro Zone einen Prozess beziehungsweise eine Instanz. Eine gleichzeitig
eintreffende Aktualisierungsanfrage erhält einen temporären Fehler, solange eine
Aktualisierung läuft.

Um die Anwendung zu aktualisieren, lade den neuen Quellcode herunter und führe
diese Befehle in dessen Verzeichnis aus. Deine Konfiguration unter `/etc` bleibt
erhalten:

```sh
sudo systemctl stop dyndns-hcloud
sudo /opt/dyndns-hcloud/venv/bin/python -m pip install --upgrade .
sudo cp deploy/dyndns-hcloud.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start dyndns-hcloud
```

### Verhalten bei Aktualisierungen und Fehlerbehebung

Verfolge den Fortschritt mit `sudo journalctl -u dyndns-hcloud -f`. Das Journal
zeigt die Validierung, die Suche nach Zonen und Einträgen, das Erstellen, Ändern
oder Überspringen jedes Eintrags, TTL-Änderungen, das Warten auf
Hetzner-Aktions-IDs und die verstrichenen Zeiten. Die abschließende Zusammenfassung
nennt die Anzahl geänderter und unveränderter Einträge. Jede Anfrage protokolliert
die IPv4-/IPv6-Adresse der Gegenstelle; bei authentifizierten Anfragen werden
zusätzlich die empfangenen Werte für `ipaddr`, `ip6addr` und `ip6lanprefix` vor der
Validierung protokolliert. Leere Werte erscheinen als `''`, fehlende Parameter als
`'<missing>'`. Steuerzeichen werden maskiert und Werte mit mehr als 128 Zeichen
gekürzt.

Hinter einem Reverse Proxy wird dessen Adresse als Quelle protokolliert; der
Dienst vertraut `X-Forwarded-For` nicht. Die Protokolle enthalten außerdem die
verwalteten DNS-Namen und Zieladressen, aber keine Zugangsdaten, Anfrage-URLs,
Eintragskommentare oder Inhalte von API-Fehlerantworten.

Änderungen werden nacheinander verarbeitet. Dabei wird jede Hetzner-Aktion
abgewartet, bevor die nächste Änderung beginnt. Mehrere Änderungen können daher
einige zehn Sekunden dauern. Die Zeitangaben zeigen, ob die Verzögerung bei einer
API-Anfrage oder beim Abfragen des Aktionsstatus entsteht; die Ablaufzeit von
DNS-Resolver-Caches ist darin nicht enthalten.

| Parameter | FRITZ!Box-Platzhalter | Aktualisiert |
| --- | --- | --- |
| `ipaddr` | `<ipaddr>` | A-Eintrag der Hauptdomain und Clients mit aktiviertem IPv4 |
| `ip6addr` | `<ip6addr>` | AAAA-Eintrag der Hauptdomain |
| `ip6lanprefix` | `<ip6lanprefix>` | AAAA-Einträge der Clients |

Diese Parameter können unabhängig voneinander gesendet werden. Fehlende oder leere
Werte lassen die zugehörigen Einträge unverändert; mindestens einer muss angegeben
werden. Nicht leere, ungültige Werte führen dazu, dass die gesamte
Aktualisierungsanfrage vor jeglichen DNS-API-Anfragen zurückgewiesen wird.
`hostname` muss die Zone oder den vollständig qualifizierten Domainnamen (FQDN)
eines konfigurierten Clients bezeichnen; jede akzeptierte Aktualisierungsanfrage
aktualisiert alle konfigurierten Namen für die übermittelten Adressen.
HEAD-/POST-Anfragen aktualisieren niemals DNS. Aus der Quell-IP der HTTP-Anfrage
wird keine Adresse abgeleitet.

| Antwort | Bedeutung |
| --- | --- |
| `good` (200) | Angeforderte Eintrags-/TTL-Änderungen über die API abgeschlossen |
| `nochg` (200) | Keine Änderungen erforderlich |
| `badauth` (401) | Fehlende oder ungültige Zugangsdaten |
| `nohost` (400) | Hostname gehört nicht zu den konfigurierten Namen |
| `notfqdn` (400) | Ungültige, doppelte oder fehlende Adressparameter |
| `911` (503) | API-Fehler, fehlgeschlagene Aktion, Zeitüberschreitung einer Aktion oder bereits laufende Aktualisierung |

Der Dienst prüft Hetzner bei jeder Aktualisierungsanfrage und überspringt
unveränderte Einträge. Aktualisierungen sind über mehrere Record-Sätze hinweg nicht
transaktional: Bei einem Fehler können einige Einträge bereits aktualisiert sein;
eine spätere Anfrage gleicht die verbleibenden Änderungen ab. Es gibt weder eine
Warteschlange für Wiederholungsversuche im Hintergrund noch einen persistenten
Adresscache.

Der Abschluss auf API-Seite bedeutet nicht, dass jeder Resolver seinen Cache
bereits erneuert hat; die TTL steuert die reguläre Zwischenspeicherung. API-Anfragen
haben ein Zeitlimit von 10 Sekunden, und das Abfragen des Aktionsstatus ist auf
30 Versuche pro Änderung begrenzt. Plane bei vielen konfigurierten Einträgen ein
ausreichendes Proxy-Zeitlimit für die nacheinander ausgeführten Aktualisierungen ein.

### Entwicklung und Referenzen

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

Die Tests decken Adressberechnung, Konfiguration, Authentifizierung, die Verarbeitung
von Aktualisierungsanfragen und den echten `hcloud`-Client mit simulierten
HTTP-Antworten ab. Sie verändern niemals echte DNS-Einträge.

- [FRITZ!Box-Platzhalter](https://fritz.com/en/apps/knowledge-base/fritz-box-7690/30_Setting-up-dynamic-DNS-in-the-FRITZ-Box)
- [Hetzner-Client für Zonen und RRSets](https://hcloud-python.readthedocs.io/en/latest/api.clients.zones.html)
- [Modified EUI-64: RFC 4291, Anhang A](https://www.rfc-editor.org/rfc/rfc4291#appendix-A)
