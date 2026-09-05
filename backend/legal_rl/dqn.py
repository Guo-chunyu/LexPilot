"""Minimal PyTorch DQN components: network, replay buffer and training loop."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Callable

import numpy as np
import torch
from torch import nn

from backend.legal_rl.actions import LegalAction


class DQNNetwork(nn.Module):
    def __init__(self, input_dim: int = 8, output_dim: int = len(LegalAction), hidden_dim: int = 64) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.network(inputs)


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


class ReplayBuffer:
    def __init__(self, capacity: int = 10_000, seed: int = 42) -> None:
        self.buffer: deque[Transition] = deque(maxlen=capacity)
        self.random = Random(seed)

    def push(self, state, action, reward, next_state, done) -> None:
        self.buffer.append(Transition(
            state=np.asarray(state, dtype=np.float32),
            action=int(action),
            reward=float(reward),
            next_state=np.asarray(next_state, dtype=np.float32),
            done=bool(done),
        ))

    def sample(self, batch_size: int):
        batch = self.random.sample(list(self.buffer), batch_size)
        return (
            np.stack([item.state for item in batch]),
            np.asarray([item.action for item in batch], dtype=np.int64),
            np.asarray([item.reward for item in batch], dtype=np.float32),
            np.stack([item.next_state for item in batch]),
            np.asarray([item.done for item in batch], dtype=np.float32),
        )

    def __len__(self) -> int:
        return len(self.buffer)


def train_dqn(
    env_factory: Callable[[], object],
    episodes: int = 100,
    batch_size: int = 32,
    gamma: float = 0.95,
    learning_rate: float = 1e-3,
    epsilon_start: float = 1.0,
    epsilon_end: float = 0.05,
    epsilon_decay: float = 0.97,
    target_update: int = 10,
    seed: int = 42,
    hidden_dim: int = 64,
) -> tuple[DQNNetwork, list[float]]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random = Random(seed)
    env = env_factory()
    policy_net = DQNNetwork(hidden_dim=hidden_dim)
    target_net = DQNNetwork(hidden_dim=hidden_dim)
    target_net.load_state_dict(policy_net.state_dict())
    target_net.eval()
    optimizer = torch.optim.Adam(policy_net.parameters(), lr=learning_rate)
    loss_fn = nn.SmoothL1Loss()
    replay = ReplayBuffer(seed=seed)
    epsilon = epsilon_start
    episode_rewards: list[float] = []

    for episode in range(episodes):
        state, _ = env.reset(seed=seed + episode)
        total = 0.0
        for _ in range(env.max_steps):
            from backend.legal_rl.policy import valid_actions
            allowed = valid_actions(env.state)
            if random.random() < epsilon:
                action = random.choice(allowed).value
            else:
                with torch.no_grad():
                    q_values = policy_net(torch.as_tensor(state).unsqueeze(0)).squeeze(0)
                    masked = torch.full_like(q_values, float("-inf"))
                    for candidate in allowed:
                        masked[candidate.value] = q_values[candidate.value]
                    action = int(masked.argmax().item())
            next_state, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
            replay.push(state, action, reward, next_state, done)
            state = next_state
            total += reward

            if len(replay) >= batch_size:
                states, actions, rewards, next_states, dones = replay.sample(batch_size)
                state_t = torch.as_tensor(states)
                action_t = torch.as_tensor(actions).unsqueeze(1)
                reward_t = torch.as_tensor(rewards)
                next_t = torch.as_tensor(next_states)
                done_t = torch.as_tensor(dones)
                q_values = policy_net(state_t).gather(1, action_t).squeeze(1)
                with torch.no_grad():
                    next_values = target_net(next_t).max(dim=1).values
                    targets = reward_t + gamma * next_values * (1.0 - done_t)
                loss = loss_fn(q_values, targets)
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(policy_net.parameters(), 5.0)
                optimizer.step()

            if done:
                break
        episode_rewards.append(round(total, 4))
        epsilon = max(epsilon_end, epsilon * epsilon_decay)
        if (episode + 1) % target_update == 0:
            target_net.load_state_dict(policy_net.state_dict())
    return policy_net, episode_rewards


def save_dqn(model: DQNNetwork, path: str | Path, *, hidden_dim: int = 64, metadata: dict | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "input_dim": 8,
        "output_dim": len(LegalAction),
        "hidden_dim": hidden_dim,
        "metadata": metadata or {},
    }, target)
    return target
