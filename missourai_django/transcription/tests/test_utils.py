class FakeLLM:
    def __init__(self, scripted_results):
        self.scripted_results = scripted_results
        self.invocations = []

    def with_structured_output(self, _schema):
        return self
    
    def __call__(self, prompt):
        return self.invoke(prompt)

    def invoke(self, prompt):
        self.invocations.append(prompt)
        try:
            return self.scripted_results.pop(0)
        except IndexError:
            raise AssertionError("FakeLLm ran out of scripted responses")
