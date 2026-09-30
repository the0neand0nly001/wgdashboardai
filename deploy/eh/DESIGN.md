# Endless VPN design

The application serves one administrator managing two private VPNs. The main
navigation is Overview, Devices and Public ports, with a persistent server
selector. Upstream administration tools remain in the Tools drawer.

The supplied Endless icon is used unchanged. Its near-black background anchors
the interface; blue represents upload and links, amber represents download and
primary actions. Status also has a text label. Dividers and aligned type organize
the content instead of repeating rounded cards, shadows or decorative effects.

## References inspected

- [Tailscale device management](https://tailscale.com/docs/features/access-control/device-management/how-to/filter):
  strong device-name hierarchy, secondary addresses and search above a flat table.
- [NetBird peer management](https://docs.netbird.io/manage/peers/add-machines-to-your-network):
  compact dark navigation, visible row states and one restrained action accent.
- [Grafana time-series example](https://play.grafana.org/d/000000016/1-time-series-graphs?orgId=1):
  meaningful legends, labeled scales and time controls connected to the graph.

The former home page gave equal weight to repeated rounded panels and outlined
metrics. Its navigation mixed common tasks with rare tools, and a text-only
header gave it little identity. The replacement gives traffic the main area,
keeps both server summaries in a narrow column, and places a searchable device
ledger beneath them. Forwarding uses a lease ledger beside an allocation form;
phones place the form first and convert device rows to labeled fields.

## Verification

The production Vue build passed. Desktop and a 390 x 844 real-app iframe were
reviewed in the browser, including search, activity filters, server switching,
time ranges, login and the Tools drawer. The iframe measured 390px document and
scroll width. Keyboard Escape closes Tools and restores focus; the drawer traps
Tab and makes the main area inert. Controls have visible focus outlines and the
interface respects reduced motion. Charts resize without shrinking their type.

The preview is explicitly labeled as sample data. Its allocation, custom duration,
renew and close workflow was checked with simulated forwarding. This does not
verify actual public forwarding, which still requires the live hosts and OCI
ingress rules. Seventeen backend checks pass for authentication, routing, lease
validation and migration preservation.
