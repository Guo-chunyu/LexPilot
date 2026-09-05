from pathlib import Path

import numpy as np

from backend.legal_rl.dqn import DQNNetwork, ReplayBuffer, save_dqn
from backend.legal_rl.policy import RLPolicy
from backend.legal_rl.state import CaseState


def test_replay_buffer_and_dqn_save_load(tmp_path: Path):
    replay = ReplayBuffer(capacity=10)
    for index in range(4):
        replay.push(np.zeros(8), index, 1.0, np.ones(8), False)
    states, actions, rewards, next_states, dones = replay.sample(2)
    assert states.shape == (2, 8)
    assert actions.shape == (2,)
    assert next_states.shape == (2, 8)

    path = save_dqn(DQNNetwork(), tmp_path / "baseline.pt")
    policy = RLPolicy.load(path, allow_fallback=False)
    assert policy.model is not None
    assert policy.predict(CaseState()).value in range(10)

