# Running unattended

Scripts that run on a timer, from cron, or over ssh to other hosts fail in ways that a person at a
terminal never sees. Three lessons from real field runs, each as a rule and a one-line check.

## 1. Timers need a calendar trigger that survives a restart

A systemd timer with only monotonic triggers (`OnBootSec=` and `OnUnitActiveSec=`) can show
`active` with **no next run** after the user manager restarts. Both deadlines were already in the
past when the timer was loaded, so it never fires again, and nothing reports an error. `Persistent=true`
only applies to `OnCalendar=`, so it does not rescue the monotonic triggers.

- **Rule:** for "every N minutes, forever", add `OnCalendar=*:0/N` with `Persistent=true`, or use it
  in place of the monotonic triggers.
- **Check:** `systemctl --user list-timers <unit>` must show a `NEXT` time. An installer or status
  command should treat "active but no next run" as a failure.

```ini
[Timer]
OnCalendar=*:0/15
Persistent=true
```

## 2. Back-to-back ssh connections get reset by hardened hosts

A script that opens one ssh connection per check can trip a host that is key-only and protected by
fail2ban or a low `MaxStartups`. After a few quick connections, the host answers
`kex_exchange_identification: Connection reset by peer` for about a minute. The checks then fail in
ways that look like the machine is down.

- **Rule:** batch the remote commands into one call (`ssh host 'cmd1; cmd2'`), or reuse one connection:
  `-o ControlMaster=auto -o ControlPath=~/.ssh/cm-%r@%h:%p -o ControlPersist=10m`. Close it with
  `ssh -O exit`.
- **Rule:** retry a connection reset with backoff, and report it as "rate-limited", not "down".
- **Check:** count the connections a run makes against the host. One run should open one connection.

## 3. Resolving a new name too early caches NXDOMAIN

Looking up a DNS name before its record is published can poison the resolvers between you and the
authority. A negative answer is cached for the zone's SOA minimum, often 30 minutes or more. The
service is up, but clients on that resolver cannot reach it until the cache expires.

- **Rule:** after creating a name, check it against the authoritative nameserver (`dig @<ns> <name>`,
  with `<ns>` from the zone's SOA) or bypass DNS (`curl --resolve <name>:443:<ip> https://<name>/`).
  Do not query it through a shared caching resolver until it is published.
- **Diagnosis:** if a public resolver (`dig @1.1.1.1 <name>`) or the authority answers, but your local
  resolver returns NXDOMAIN with an SOA in the AUTHORITY section, the negative answer is cached. The
  SOA's TTL shows how long it lasts. Flush the resolver's cache, or limit the damage with a short
  negative TTL (dnsmasq: `neg-ttl=60`).
