import pygame
import numpy as np
import torch
import torch.nn as nn
import random
from collections import deque

# Pygame setup
pygame.init()
WIDTH, HEIGHT = 600, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Traffic Signal Control with DQN")
clock = pygame.time.Clock()

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# Traffic environment
class TrafficEnv:
    def _init_(self):
        self.lanes = {'N': [], 'S': [], 'E': [], 'W': []}  # List of vehicle positions
        self.vehicle_count = {'N': 0, 'S': 0, 'E': 0, 'W': 0}  # Count of vehicles
        self.signal = 0  # 0: N-S green, 1: E-W green
        self.phase_time = 0
        self.max_vehicles = 10
        self.step_count = 0

    def reset(self):
        self.lanes = {'N': [], 'S': [], 'E': [], 'W': []}
        self.vehicle_count = {'N': 0, 'S': 0, 'E': 0, 'W': 0}
        self.signal = 0
        self.phase_time = 0
        self.step_count = 0
        self._spawn_vehicles()
        return self._get_state()

    def _spawn_vehicles(self):
        for _ in range(random.randint(0, 4)):
            lane = random.choice(['N', 'S', 'E', 'W'])
            if self.vehicle_count[lane] < self.max_vehicles:
                self.lanes[lane].append(300 - (self.vehicle_count[lane] * 40))
                self.vehicle_count[lane] += 1

    def step(self, action):
        self.step_count += 1
        # Action: 0 (N-S green), 1 (E-W green), 2 (extend)
        if action == 0:
            self.signal = 0
            self.phase_time = 0
        elif action == 1:
            self.signal = 1
            self.phase_time = 0
        else:
            self.phase_time += 1

        # Move vehicles
        for lane in ['N', 'S', 'E', 'W']:
            can_move = (lane in ['N', 'S'] and self.signal == 0) or (lane in ['E', 'W'] and self.signal == 1)
            new_positions = []
            for pos in self.lanes[lane]:
                if can_move and pos < 300:
                    pos += 5  # Move toward intersection
                if pos <= 600:  # Keep vehicles within screen
                    new_positions.append(pos)
                else:
                    self.vehicle_count[lane] -= 1  # Vehicle exits
            self.lanes[lane] = new_positions

        # Spawn new vehicles
        if self.step_count % 10 == 0:
            self._spawn_vehicles()

        # State, reward, done
        state = self._get_state()
        reward = -sum(self.vehicle_count.values()) - (0.1 if action < 2 else 0)
        done = self.step_count > 200
        return state, reward, done

    def _get_state(self):
        return np.array([
            self.vehicle_count['N'], self.vehicle_count['S'],
            self.vehicle_count['E'], self.vehicle_count['W'],
            self.signal, self.phase_time / 10.0
        ])

    def render(self):
        screen.fill(WHITE)
        # Draw roads
        pygame.draw.rect(screen, BLACK, (0, 250, 600, 100))  # E-W road
        pygame.draw.rect(screen, BLACK, (250, 0, 100, 600))  # N-S road
        # Draw vehicles
        for lane, positions in self.lanes.items():
            for pos in positions:
                if lane == 'N':
                    pygame.draw.rect(screen, BLUE, (275, pos, 20, 30))
                elif lane == 'S':
                    pygame.draw.rect(screen, BLUE, (305, 600 - pos, 20, 30))
                elif lane == 'E':
                    pygame.draw.rect(screen, BLUE, (600 - pos, 275, 30, 20))
                elif lane == 'W':
                    pygame.draw.rect(screen, BLUE, (pos, 305, 30, 20))
        # Draw signals
        ns_color = GREEN if self.signal == 0 else RED
        ew_color = GREEN if self.signal == 1 else RED
        pygame.draw.circle(screen, ns_color, (250, 250), 10)
        pygame.draw.circle(screen, ns_color, (350, 350), 10)
        pygame.draw.circle(screen, ew_color, (250, 350), 10)
        pygame.draw.circle(screen, ew_color, (350, 250), 10)
        pygame.display.flip()

# DQN Model
class DQN(nn.Module):
    def _init_(self, state_dim, action_dim):
        super(DQN, self)._init_()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, action_dim)
        )

    def forward(self, x):
        return self.net(x)

# Replay Buffer
class ReplayBuffer:
    def _init_(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def add(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (np.array(states), np.array(actions), np.array(rewards),
                np.array(next_states), np.array(dones))

# DQN Agent
class DQNAgent:
    def _init_(self, state_dim, action_dim):
        self.model = DQN(state_dim, action_dim)
        self.target_model = DQN(state_dim, action_dim)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        self.memory = ReplayBuffer(10000)
        self.gamma = 0.99
        self.epsilon = 1.0
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.1
        self.batch_size = 32
        self.update_target_freq = 100
        self.steps = 0

    def act(self, state):
        if random.random() < self.epsilon:
            return random.randint(0, 2)
        state = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(state)
        return q_values.argmax().item()

    def train(self):
        if len(self.memory.buffer) < self.batch_size:
            return
        states, actions, rewards, next_states, dones = self.memory.sample(self.batch_size)
        states = torch.FloatTensor(states)
        actions = torch.LongTensor(actions)
        rewards = torch.FloatTensor(rewards)
        next_states = torch.FloatTensor(next_states)
        dones = torch.FloatTensor(dones)

        q_values = self.model(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        next_q_values = self.target_model(next_states).max(1)[0]
        targets = rewards + self.gamma * next_q_values * (1 - dones)

        loss = nn.MSELoss()(q_values, targets)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        self.steps += 1
        if self.steps % self.update_target_freq == 0:
            self.target_model.load_state_dict(self.model.state_dict())

        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

# Main loop
env = TrafficEnv()
agent = DQNAgent(state_dim=6, action_dim=3)
episodes = 500
running = True

for episode in range(episodes):
    state = env.reset()
    total_reward = 0
    step = 0
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        action = agent.act(state)
        next_state, reward, done = env.step(action)
        env.render()
        agent.memory.add(state, action, reward, next_state, done)
        agent.train()

        state = next_state
        total_reward += reward
        step += 1
        clock.tick(30)

        if done:
            break

    print(f"Episode {episode + 1}, Total Reward: {total_reward:.2f}, Epsilon: {agent.epsilon:.2f}")
    if not running:
        break

pygame.quit()