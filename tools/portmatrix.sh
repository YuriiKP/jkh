#!/usr/bin/env bash
# Матрица TCP/UDP доступности цели с этого хоста (ноды xray).
#   ./portmatrix.sh <DST_IP> [iface|auto|direct]
#   auto   — найти tun/wg-интерфейс (по умолчанию; на docker-ноде его не будет)
#   direct — без привязки: путь тот же, что у ноды (outbound freedom), т.е. это и есть egress VPN-клиента
#   wg0/tun0/... — привязаться к конкретному интерфейсу
#   sudo нужен для -sS/-sU
DST=${1:?usage: $0 <IP> [iface|auto|direct]}
MODE=${2:-auto}
[ "$MODE" = auto ] && MODE=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(wg|tun|tap|ppp|nordlynx|proton|tailscale)' | head -1)
[ "$MODE" = direct ] && MODE=""
if [ -n "$MODE" ] && ! ip link show "$MODE" >/dev/null 2>&1; then
  echo "!! интерфейса '$MODE' нет. Доступные:"; ip -br a; exit 1
fi
IF=$MODE
B=();  [ -n "$IF" ] && B=(-I "$IF")
NE=(); [ -n "$IF" ] && NE=(-e "$IF")
CB=(); [ -n "$IF" ] && CB=(--interface "$IF")

# 1443/3443/5443/9443/11443/12443/13443 — альтернативы 443, типичные для обхода блокировки 443
TCP=${TCP_PORTS:-22,25,53,80,110,143,443,465,587,993,995,1443,3306,3389,3443,5443,8080,8443,9443,11443,12443,13443}
UDP=${UDP_PORTS:-53,123,443,500,1194,1443,3443,3478,4500,5443,9443,11443,12443,13443,51820}
P=${PROBE_PORT:-443}

echo "== iface: ${IF:-direct (без привязки)}"
echo "== route: $(ip route get "$DST" | head -1)"
echo "== egress: $(curl -s --max-time 8 "${CB[@]}" https://ifconfig.me || echo FAIL)"
echo "== ping:"; ping -c 4 -W 2 "${B[@]}" "$DST" | tail -2

echo "== TCP:";       sudo nmap -Pn -sS "${NE[@]}" --reason --max-retries 1 -p "$TCP" --host-timeout 120s "$DST" | grep -E '^[0-9]+/tcp'
echo "== TCP/$P x20:"; ok=0; for i in $(seq 20); do timeout 4 bash -c "exec 3<>/dev/tcp/$DST/$P" 2>/dev/null && ok=$((ok+1)); done; echo "$ok/20 open"
echo "== UDP:";       sudo nmap -Pn -sU "${NE[@]}" --reason --max-retries 1 -p "$UDP" --host-timeout 180s "$DST" | grep -E '^[0-9]+/udp'
echo "== control:";   nc -vz -w 5 1.1.1.1 443 2>&1 | tail -1
dig +time=3 +tries=1 @1.1.1.1 example.com +short >/dev/null && echo "udp/53 ok"
