class MyTestClass:
    """
    Immutable Memento-like representation of an aggregate
    Always has id.
    """

    def __init__(self, param: int):
        """
        Constructor
        :param param: some init param
        """
        self.param = param

    def get(self) -> int:
        """
        Get memento id
        :return: memento id
        """
        return 0
