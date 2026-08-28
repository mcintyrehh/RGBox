class WizSocket:
    def __init__(self, pool, ip, port):
        self.pool = pool
        self.ip = ip
        self.port = port
        self.sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)

    def send(self, msg):
        try:
            self.sock.sendto(msg.encode(), (self.ip, self.port))
        except (BrokenPipeError, OSError):
            self.sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_DGRAM)
            self.sock.sendto(msg.encode(), (self.ip, self.port))