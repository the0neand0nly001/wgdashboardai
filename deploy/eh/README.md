# Endless Horizons: one dashboard on Oracle VPN2

The browser uses `http://10.8.1.0:8787` from either existing VPN. The existing
VPN-only proxies and host-key-pinned SSH link stay in place. Only VPN2 runs the
gateway and the shared admin login. Choose Oracle VPN1 or Oracle VPN2 in the top
bar to manage that server. Node tokens stay on the servers.

Each host also runs a private WGDashboard backend attached to its existing
`amnezia-wireguard` network namespace and a loopback-only bridge at port 8791.
The backend listens only on Amnezia's Docker bridge IPv4 address at port 10086.
A dedicated `EHWGD_BACKEND` input chain accepts that port only from the host's
Docker bridge gateway and drops it from VPN devices and other containers. Every
backend request also requires its node token. No backend port is published.
The node needs neither host PID access nor SYS_ADMIN/SYS_PTRACE privileges;
it connects over this filtered private network and retains NET_ADMIN for its
dedicated forwarding rules. The Docker socket is still a trusted administration
interface and must remain private.
VPN2 reaches VPN1's bridge through SSH at localhost:18791. Both configurations
use standard WireGuard, `wg0`, and `/opt/amnezia/wireguard/wg0.conf`, verified
on both hosts. Each backend receives its public IP so exported profiles never
use Docker's private bridge address.

## Current status

2026-10-01: the replacement is running through the two Git-backed Komodo stacks,
`eh-wgdashboard-vpn1` and `eh-wgdashboard-vpn2`. VPN2 hosts the shared login and
gateway. Both native backends import their existing peers successfully. The
original public Amnezia UDP ports, stopped rollback containers and root-only
config backups are retained. The old dashboard is stopped and its data is backed
up. Rathole and other stacks were not changed.

Disposable WireGuard clients connected to both servers using native exported
profiles and reached the same private dashboard address. The shared login,
server switching, QR generation, unauthenticated API rejection and private
backend isolation passed live checks. TCP/UDP forwarding to each connected test
client, allocation, custom renewal, Close and automatic one-minute expiry passed.
External forwarding probes failed and did not reach the host forwarding chains:
**OCI ingress for TCP and UDP 45100–45120 remains required on both servers**.
Internet reachability must be retested after those rules are added.

See [DESIGN.md](DESIGN.md) for the visual direction, references and UI checks.

### Build away from small VPN hosts

Avoid compiling the Vue bundle on the 1 GB VPSs. Build the two images on the PC,
tag them `eh-wgdashboard-backend:local` and `eh-wgdashboard-services:local`, export
them with `docker image save`, transfer the archive through the existing SSH
connection, and verify its SHA-256 before `sudo docker image load -i ARCHIVE` on
each host. Inspect the platform first; these PC builds are Linux/amd64.
Set the two dashboard stacks' `run_build` to false and `auto_pull` to false, so
Komodo starts the imported images. Import images before deploying; an absent
image must not be substituted with the upstream public image. Recover and
inspect any existing build job before starting another deployment.

## Prepare and deploy with Komodo

1. Push this fork after reviewing the changes. Configure a Git-backed Komodo
   stack on each host, checking out the fork including the local modifications.
   Select `deploy/eh/compose.vpn1.yaml` on VPN1 and
   `deploy/eh/compose.vpn2.yaml` on VPN2. Keep the project name `eh-wgdashboard`.
   Build these images from the fork; the stock upstream image has none of the
   custom UI or services. VPN1's containerized Periphery terminal is not a host
   terminal: use your normal Ubuntu SSH session for the preparation helpers.
2. First run `sudo python3 deploy/eh/persist_amnezia.py` on each host. This
   copies the existing Amnezia config to a root-only host directory, backs it
   up and briefly recreates Amnezia with a persistent bind mount. Its exact
   existing local image, generated startup script, command, public ports, capabilities and peer config
   are preserved. The original stopped container is retained for rollback;
   startup failure triggers an automatic rollback. This migration must be
   verified with a VPN connection after each host before continuing.
   On VPN2, make a small host virtual environment with Flask available:

   ```sh
   python3 -m venv /home/ubuntu/eh-prepare-venv
   /home/ubuntu/eh-prepare-venv/bin/pip install Flask==3.1.2
   sudo /home/ubuntu/eh-prepare-venv/bin/python deploy/eh/prepare.py vpn2
   ```

   This prompts for the central admin login, creates root-only server tokens,
   and backs up the current VPN config. Transfer only the generated
   `/etc/komodo/eh-wgdashboard/vpn1-shared.env` securely to VPN1.
3. On VPN1, run:

   ```sh
   sudo python3 deploy/eh/prepare.py vpn1 --secrets /secure/path/vpn1-shared.env
   sudo python3 deploy/eh/upgrade_link.py vpn1
   ```

   On VPN2, run `sudo python3 deploy/eh/upgrade_link.py vpn2`. This extends
   only the existing restricted dashboard key/service to reach port 8791.
4. Supply `/etc/komodo/eh-wgdashboard/vpn1.env` or `vpn2.env` to the respective
   Compose invocation with `--env-file`. Keep the files on their hosts; never
   commit them or put their contents in a public repository. Preserve quoted
   values: the password hash contains dollar signs.
5. Build the images on the PC and import them on both hosts as described above.
   Start the backend and node services on both hosts first through Komodo with
   `run_build=false` and `auto_pull=false`.
   Check their logs, config import, stats and node-token authentication. The
   VPN2 gateway will fail to bind while the old dashboard owns localhost:8787;
   start it only at cutover. An equivalent direct invocation is:

   ```sh
   sudo docker compose --env-file /etc/komodo/eh-wgdashboard/vpn2.env -f deploy/eh/compose.vpn2.yaml up -d --no-build --pull never backend node
   ```

6. Back up `/etc/komodo/eh-vpn-dashboard/data`. Stop the **old dashboard
   container only**, preserving its data, proxies, collectors and SSH link.
   Start the VPN2 `gateway` service through Komodo. The existing proxies now
   reach the new login page at the same address.
7. Open `http://10.8.1.0:8787` through VPN1 and VPN2 separately. Check that
   every API/download requires login; change the server selector and verify
   peer, QR and forwarding actions use that server. Disconnect the VPN and
   confirm the page and APIs are unreachable. Do not publish a public route
   for the dashboard or private service ports.

## Forwarding

- The reserved public range is **45100–45120 on each server**, TCP and UDP.
  Add inbound rules for that exact range in the OCI security list/NSG for both
  hosts. This step is separate from the application and has not been performed.
- Choose a configured peer with one IPv4 /32 address, its local service port,
  protocol and duration (1 minute to 7 days; custom minutes and quick presets).
  The server allocates an available port. Renew replaces the deadline with
  now + the selected duration; Close removes the lease and tracked flows.
- Dedicated `EHWGD_*` chains forward through the existing container and `wg0`.
  Host filter deadlines block existing forwarded connections when a lease
  expires even if the worker stops. Rules only cover the reserved range; they
  do not replace or flush Amnezia/Docker firewall chains.
- A device must remain connected to the selected VPN and allow its local
  service in its firewall. The service is public while its lease is active.
  Source NAT means the service sees the VPN server as the connection source.
- Test TCP and UDP externally, including close, expiry, renewal and container
  restarts, before relying on this. The node agent has host administration
  privileges for Docker administration and forwarding; it binds only to loopback
  and authenticates every request.

## Data, QR codes and upkeep

The overview stores monitor totals and seven days of minute-averaged samples in
`/etc/komodo/eh-wgdashboard/node`. Totals start at installation; previous totals
are not imported. The chart displays the last day. Device labels on the home
page are saved in the browser and per server. Native peer names are stored in
the backend database. Recent activity means a handshake within 180 seconds.

QR/config exports require the device private key. Newly created dashboard
peers have one; existing Amnezia peers generally require their original client
config to be imported. Never pretend server public keys can reconstruct it.
Managing the same peers in both Amnezia and WGDashboard can cause conflicting
config edits; back up first and use one management tool per edit.

The backend shares the persistent host config directory with Amnezia. After
an Amnezia restart/recreation, recreate the affected `backend` service so it
joins the new network namespace. Preserve Amnezia's config bind mount during
updates. Namespace attachment is not automatically migrated. Plan this repair
into Amnezia updates; the private node collects from the current container.

The Account settings on either selected server edit the same central admin
login, persisted in `/etc/komodo/eh-wgdashboard/gateway/account.json`. A password
change requires the current password, a matching confirmation and at least 8
characters. It invalidates other existing sessions. Native backend MFA is not
used by the gateway and its controls are hidden to avoid implying it protects
the shared login. All VPN management tools remain behind the login and menu.

For rollback, stop the new gateway and restart `eh-vpn-dashboard` in Komodo.
The VPN-only proxies and existing SSH routes still point to localhost:8787.
Close all new forwarding leases before removing the node service. Preserve
both old and new data directories and the VPN config backups.
