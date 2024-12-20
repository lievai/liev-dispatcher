class FimNotSupportedException(Exception):
    def __init__(self, message="Fill in the middle not supported for this LLM"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'FimNotSupportedException: {self.message}'
    
class HttpStreamingNotSupportedException(Exception):
    def __init__(self, message="Http streaming is not supported for this LLM"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'HttpStreamingNotSupportedException: {self.message}'
    
