from abc import ABC, abstractmethod


class BaseDQEngine(ABC):
    @abstractmethod
    def run_rule(self, data, rule: dict) -> dict:
        raise NotImplementedError
