from collections import namedtuple
from time import sleep
from unittest import TestCase

import gym.spaces as spaces
import torch as T
import torch.nn as nn
import torch.optim as optim

from pandas_ml_quant import np, PostProcessedFeaturesAndLabels
from pandas_ml_quant_rl.cache import FileCache
from pandas_ml_quant_rl.model.environments.multi_symbol_environment import RandomAssetEnv
from pandas_ml_quant_rl.model.strategies.discrete import BuyOpenSellCloseSellOpenBuyClose
from pandas_ml_quant_rl.renderer import OnlineRenderer, CandleStickRenderer
from pandas_ml_quant_rl_test.config import load_symbol
from pandas_ml_utils.pytorch import Reshape


class TestAgents(TestCase):

    def test_reinforce(self):

        env = RandomAssetEnv(
            PostProcessedFeaturesAndLabels(
                features=[
                    lambda df: df.ta.candle_category().ta.one_hot_encode_discrete(offset=-15, nr_of_classes=30)
                ],
                labels=[
                    # note that log returns are additive which is what we do with the reward
                    lambda df: np.log(df["Close"] / df["Open"]).rename("day return").shift(-1)
                ],
                feature_post_processor=[
                    lambda df: df.ta.rnn(10)
                ],
            ),
            ["SPY", "GLD"],
            strategy=BuyOpenSellCloseSellOpenBuyClose(),
            pct_train_data=0.8,
            max_steps=50,
            min_training_samples=50,
            use_cache=FileCache('/tmp/agent.test.dada.hd5', load_symbol),
        )

        # try to train this stuff
        HIDDEN_SIZE = 128
        BATCH_SIZE = 16
        PERCENTILE = 70

        # define neural network to estimate a policy
        class Net(nn.Module):
            def __init__(self, obs_size, hidden_size, n_actions):
                super(Net, self).__init__()
                flattened_obs_size = np.array(obs_size).prod()
                self.net = nn.Sequential(
                    Reshape(flattened_obs_size),
                    nn.Linear(flattened_obs_size, hidden_size),
                    nn.ReLU(),
                    nn.Linear(hidden_size, n_actions)
                )

            def forward(self, x):
                return self.net(T.FloatTensor(x))

        Episode = namedtuple('Episode', field_names=['reward', 'steps'])
        EpisodeStep = namedtuple('EpisodeStep', field_names=['observation', 'action'])

        # env = gym.wrappers.Monitor(env, directory="mon", force=True)
        obs_size = env.observation_space.shape
        n_actions = env.action_space.n
        net = Net(obs_size, HIDDEN_SIZE, n_actions)


        objective = nn.CrossEntropyLoss()
        optimizer = optim.Adam(params=net.parameters(), lr=0.01)
        #writer = SummaryWriter(comment="-stocks")

        print(env.step(env.action_space.sample()))
        sm = nn.Softmax(dim=1)

        # play BATCH_SIZE episodes using random actions and store all trajectories
        def iterate_batches(env, net, batch_size):
            episode_reward = 0.0
            episode_steps = []
            batch = []

            # start new game and get initial state
            obs = env.reset()

            while True:
                # convert series to tensor
                np_obs = obs._.values
                obs_v = T.FloatTensor(np_obs)

                # use network to get probabilities of  actions
                act_probs_v = sm(net(obs_v))

                # convert back to numpy and get rid of batch dimension
                act_probs = act_probs_v.data.numpy()[0]

                # decide for a random action and execute it and collect the reward
                action = np.random.choice(len(act_probs), p=act_probs)
                next_obs, reward, is_done, _ = env.step(action)
                episode_reward += reward

                # remember in which state we were and which action ww took
                episode_steps.append(EpisodeStep(observation=np_obs[0], action=action))

                # we play until we die, batch_size games will be collected into one batch
                # each batch has a different length of steps and actions
                if is_done:
                    batch.append(Episode(reward=episode_reward, steps=episode_steps))
                    episode_reward = 0.0
                    episode_steps = []
                    next_obs = env.reset()
                    if len(batch) == batch_size:
                        yield batch
                        batch = []
                obs = next_obs

        def filter_batch(batch, percentile):
            rewards = list(map(lambda s: s.reward, batch))
            reward_bound = np.percentile(rewards, percentile)
            reward_mean = float(np.mean(rewards))

            train_obs = []
            train_act = []
            for example in batch:
                if example.reward < reward_bound:
                    continue
                train_obs.extend(map(lambda step: step.observation, example.steps))
                train_act.extend(map(lambda step: step.action, example.steps))

            train_obs_v = T.FloatTensor(train_obs)
            train_act_v = T.LongTensor(train_act)
            return train_obs_v, train_act_v, reward_bound, reward_mean

        for iter_no, batch in enumerate(iterate_batches(env, net, BATCH_SIZE)):
            obs_v, acts_v, reward_b, reward_m = filter_batch(batch, PERCENTILE)
            optimizer.zero_grad()
            action_scores_v = net(obs_v)

            # since each batch contains different trajectory of steps and actions we will have different batch sizes for
            # each batch of episodes!
            # NOTE the CrossEntropyLoss expects raw logits as input (raw probabilities for each action)
            # and an integer of the correct action. if the labels would be one hot encoded we would need an argmax!
            loss_v = objective(action_scores_v, acts_v)
            loss_v.backward()
            optimizer.step()


            print("%d: loss=%.3f, reward_mean=%.1f, reward_bound=%.1f performance=%.2f" % (
                iter_no, loss_v.item(), reward_m * 100, reward_b * 100, 0.0))
            #writer.add_scalar("loss", loss_v.item(), iter_no)
            #writer.add_scalar("reward_bound", reward_b, iter_no)
            #writer.add_scalar("reward_mean", reward_m, iter_no)
            if iter_no > 20:
                print("Solved!")
                break
        #writer.close()



        render_engine = OnlineRenderer(lambda: CandleStickRenderer(
            action_mapping=[(1, 'buy', 'Open'), (1, 'sell', 'Close'), (2, 'sell', 'Open'), (2, 'buy', 'Close')]))
        render_engine.render()

        # test what we have learned
        test_env, obs = env.as_test(render_engine)

        test_done = False
        test_reward = 0
        while not test_done:
            np_obs = obs._.values
            obs_v = T.FloatTensor(np_obs)
            act_probs_v = sm(net(obs_v))
            act_probs = act_probs_v.data.numpy()[0]
            print(f"act probs: {act_probs}")

            action = np.random.choice(len(act_probs), p=act_probs)
            obs, episode_reward, test_done, _ = test_env.step(action)
            test_reward += episode_reward

        print(f"test reward: {test_reward}")
        sleep(2)
        render_engine.stop()

