import time

# Don't hammer a bulb that isn't answering; wait this long before trying again.
RETRY_INTERVAL = 5


class WizSocket:
    def __init__(self, pool, ip, port):
        self.pool = pool
        self.ip = ip
        self.port = port
        self.sock = self._new_socket()
        self.retry_after = 0

    def _new_socket(self):
        return self.pool.socket(self.pool.AF_INET, self.pool.SOCK_DGRAM)

    def send(self, msg):
        """Fire-and-forget a UDP message. Never raises.

        A bulb that is powered off replies with an ICMP destination-unreachable,
        which lwIP reports on the next sendto() as OSError 32 (EPIPE). Recreating
        the socket clears that state, but if the bulb is still off the retry fails
        the same way, so we swallow it and back off instead of crashing.
        """
        if time.monotonic() < self.retry_after:
            return False

        data = msg.encode()
        for attempt in range(2):
            try:
                self.sock.sendto(data, (self.ip, self.port))
                return True
            except OSError as e:
                if attempt == 0:
                    # Stale socket error - rebuild and try once more.
                    try:
                        self.sock.close()
                    except OSError:
                        pass
                    self.sock = self._new_socket()
                else:
                    print(f"wiz {self.ip} unreachable ({e}), retrying in {RETRY_INTERVAL}s")
                    self.retry_after = time.monotonic() + RETRY_INTERVAL

        return False
