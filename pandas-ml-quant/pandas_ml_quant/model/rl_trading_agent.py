from typing import Callable

from pandas_ml_utils import ReinforcementModel, FeaturesAndLabels
from gym.spaces import MultiDiscrete, Box
from pandas_ml_common import np, pd, Typing

from pandas_ml_utils.ml.summary import Summary


class TradingAgentGym(ReinforcementModel.DataFrameGym):

    def __init__(self,
                 input_shape,
                 initial_capital=100000,
                 commission=lambda size: 0.025):
        super().__init__(MultiDiscrete([3, 10]), # [buy|hold|sell, n/10]
                         Box(low=-1, high=1, shape=input_shape)) # FIXME what shape? we also need historic trades?

        self.initial_capital = initial_capital
        self.commission_calculator = commission

        # place holder variables setted by reset function
        # TODO add some observations to the observation space i.e.
        #   our net worth, the amount of BTC bought or sold, and the total amount in USD we’ve spent on or received
        #   from those BTC.
        self.capital = None
        self.trades = None

    def reset(self):
        self.trades = []
        self.capital = self.initial_capital
        return super().reset()

    def take_action(self, action, idx, features, labels) -> float:
        if action < 1:
            # hold
            pass
        elif action < 2:
            # buy
            pass
        elif action < 3:
            # sell
            pass
        else:
            raise ValueError(f"unkown action {action}!")

        # FIXME currently returns fake award
        # TODO throw a value error if bankrupt
        return 0.1

    def next_observation(self, idx, x) -> np.ndarray:
        # FIXME currently returns only the features, but we also want to return some net worth, history, ...
        return x

    def render(self, mode='human'):
        if mode == 'system':
            # TODO print something
            pass
        elif mode == 'notebook':
            # TODO plot something using matplotlib
            pass
        elif mode == 'human':
            # TODO plot something using matplotlib
            pass


class RLTradingAgentModel(ReinforcementModel):

    def __init__(self,
                 reinforcement_model: Callable[[ReinforcementModel.DataFrameGym], ReinforcementModel.RLModel],
                 features_and_labels: FeaturesAndLabels,
                 input_shape,
                 initial_capital=100000,
                 commission=lambda size: 0.025,
                 summary_provider: Callable[[Typing.PatchedDataFrame], Summary] = Summary,
                 **kwargs):
        super().__init__(reinforcement_model,
                         TradingAgentGym(input_shape, initial_capital, commission),
                         features_and_labels,
                         summary_provider,
                         **kwargs)



