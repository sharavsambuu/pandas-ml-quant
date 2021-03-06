from unittest import TestCase

import numpy as np
import torch as t
import torch.nn as nn
from torch.optim import Adam

from pandas_ml_common.utils.numpy_utils import one_hot
from pandas_ml_quant import PostProcessedFeaturesAndLabels
from pandas_ml_quant.pytorch.loss import SoftDTW, DifferentiableArgmax, ParabolicPenaltyLoss, TailedCategoricalCrossentropyLoss
from pandas_ml_quant_test.config import DF_TEST
from pandas_ml_utils import AutoEncoderModel
from pandas_ml_utils.ml.model.pytoch_model import PytorchModel


class TestCustomLoss(TestCase):

    def test__differentiable_argmax(self):
        """given"""
        args = 10
        argmax = DifferentiableArgmax(args)

        """when"""

        res = np.array([argmax(t.tensor(one_hot(i, args))).numpy() for i in range(args)])

        """then"""
        print(res)
        np.testing.assert_array_almost_equal(res, np.arange(0, args))

    def test__parabolic_crossentropy(self):
        """when"""
        categories = 11
        loss_function = ParabolicPenaltyLoss(categories, 1)

        """then"""
        for truth in range(categories):
            losses = []
            for prediction in range(categories):
                loss = loss_function(t.tensor(one_hot(prediction, categories)),
                                     t.tensor(one_hot(truth, categories)))
                losses.append(loss)

            # all predictions left of truth need to increase
            for i in range(1, truth):
                self.assertGreater(losses[i - 1], losses[i])

            # right of truth need to decrease
            for i in range(truth, categories - 1):
                self.assertLess(losses[i], losses[i + 1])

            if truth > 0 and truth < categories - 1:
                if truth > categories / 2:
                    # right tail:
                    self.assertGreater(losses[truth - 1], losses[truth + 1])
                else:
                    # left tail
                    self.assertGreater(losses[truth + 1], losses[truth - 1])

    def test__tailed_categorical_crossentropy(self):
        """when"""
        categories = 11
        loss = TailedCategoricalCrossentropyLoss(categories, 1)

        """then"""
        truth = one_hot(3, 11)
        l = loss(t.tensor([one_hot(6, 11)]), t.tensor([truth]))
        l2 = loss(t.tensor([one_hot(6, 11), one_hot(9, 11)]), t.tensor([truth, truth]))

        """then"""
        np.testing.assert_almost_equal(l, 11.817837, decimal=5)
        np.testing.assert_array_almost_equal(l2, [11.817837, 42.46247], decimal=5)
        self.assertGreater(l.mean().numpy(), 0)

    def test__tailed_categorical_crossentropy_3d(self):
        loss = TailedCategoricalCrossentropyLoss(11, 1)
        self.assertEqual(loss(t.ones((32, 11), requires_grad=True), t.ones((32, 1, 11), requires_grad=True)).shape,
                         (32,))
        self.assertEqual(loss(t.ones((32, 1, 11), requires_grad=True), t.ones((32, 1, 11), requires_grad=True)).shape,
                         (32,))
        self.assertEqual(loss(t.ones((32, 11), requires_grad=True), t.ones((32, 11), requires_grad=True)).shape,
                         (32,))

    def test_soft_dtw_loss(self):
        df = DF_TEST[["Close"]][-21:].copy()

        class LstmAutoEncoder(nn.Module):
            def __init__(self):
                super().__init__()
                self.input_size = 1
                self.seq_size=10
                self.hidden_size = 2
                self.num_layers = 1
                self.num_directions = 1

                self._encoder =\
                    nn.RNN(input_size=self.input_size, hidden_size=self.hidden_size, num_layers=self.num_layers,
                           batch_first=True)

                self._decoder =\
                    nn.RNN(input_size=self.hidden_size, hidden_size=self.input_size, num_layers=self.num_layers,
                           batch_first=True)

            def forward(self, x):
                # make sure to treat single elements as batches
                x = x.view(-1, self.seq_size, self.input_size)
                batch_size = len(x)

                hidden_encoder = nn.Parameter(t.zeros(self.num_layers * self.num_directions, batch_size, self.hidden_size))
                hidden_decoder = nn.Parameter(t.zeros(self.num_layers * self.num_directions, batch_size, self.input_size))

                x, _ = self._encoder(x, hidden_encoder)
                x = t.repeat_interleave(x[:,-2:-1], x.shape[1], dim=1)
                x, hidden = self._decoder(x, hidden_decoder)
                return x

            def encoder(self, x):
                x = x.reshape(-1, self.seq_size, self.input_size)
                batch_size = len(x)

                with t.no_grad():
                    hidden = nn.Parameter(
                        t.zeros(self.num_layers * self.num_directions, batch_size, self.hidden_size))

                    # return last element of sequence
                    return self._encoder(t.from_numpy(x).float(), hidden)[0].numpy()[:,-1]

            def decoder(self, x):
                x = x.reshape(-1, self.seq_size, self.hidden_size)
                batch_size = len(x)

                with t.no_grad():
                    hidden = nn.Parameter(
                        t.zeros(self.num_layers * self.num_directions, batch_size, self.input_size))
                    return self._decoder(t.from_numpy(x).float(), hidden)[0].numpy()

        model = AutoEncoderModel(
            PytorchModel(
                PostProcessedFeaturesAndLabels(df.columns.to_list(), [lambda df: df.ta.rnn(10)],
                                               df.columns.to_list(), [lambda df: df.ta.rnn(10)]),
                LstmAutoEncoder,
                SoftDTW,
                Adam
            ),
            ["condensed-a", "condensed-b"],
            lambda m: m.module.encoder,
            lambda m: m.module.decoder,
        )

        fit = df.model.fit(model, epochs=100)
        print(fit.test_summary.df)

        encoded = df.model.predict(fit.model.as_encoder())
        print(encoded)
