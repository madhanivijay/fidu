from abc import ABC, abstractmethod


class BaseConnector(ABC):
    @abstractmethod
    def load_data(self, source_config: dict):
        raise NotImplementedError
