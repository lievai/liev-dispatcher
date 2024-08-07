class LLMMissingRequiredFieldException(Exception):
    def __init__(self, message="Missing a required field!"):
        self.message = message
        super().__init__(self.message)
