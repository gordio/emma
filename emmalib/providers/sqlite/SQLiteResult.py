class SQLiteResult(object):
    def __init__(self, result, d):
        self.result = result
        if d:
            self.description = tuple(d)
        else:
            self.description = ()

    def fetch_row(self, arg):
        return self.result

    def describe(self):
        return self.description

    def num_rows(self):
        return len(self.result)