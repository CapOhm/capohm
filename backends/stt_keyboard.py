class STT:
    def __init__(self, config, ui=None):
        self.config = config
        self.ui = ui

    def start(self):
        print("Keyboard STT active. Type your input and press Enter.")

    def listen(self):
        try:
            text = input("> ").strip()
            if text:
                if self.ui:
                    self.ui.heard(text)
                return text
        except EOFError:
            return None
        except KeyboardInterrupt:
            raise
        return None
