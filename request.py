from configs import CFG, Config
config = Config.from_json(CFG)

class HTTPRequest:
    def __init__(self, src_port, dest_port, data):

        assert len(data) <= config.constants.MAX_HTTP_BODY_SIZE, print(
            f"MAXIMUM DATA SIZE EXCEEDED. MAX SIZE ALLOWED: {config.constants.MAX_HTTP_BODY_SIZE}"
        )
        self.src_port = src_port
        self.dest_port = dest_port
        self.length = len(data)
        self.data = data
