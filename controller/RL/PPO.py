import multiprocessing as mp

class PPOController:
    def __init__(self, simulator):
        for i in range(50):
            simulator.step(0)
        self.ppo = PPO()

    def control(self, future_required_temperatures, future_outside_temperatures, future_energy_cost,
                previous_outside_temperatures, previous_inside_temperatures, previous_energy_consuption):
            future_min = [x[0] for x in future_required_temperatures]
            future_max = [x[1] for x in future_required_temperatures]
            state = future_min + future_max + future_outside_temperatures + future_energy_cost + previous_outside_temperatures + previous_inside_temperatures + previous_energy_consuption
            tf_state = tf.constant(state, name="State")
            tf_state = tf.reshape(tf_state, (1, -1))
            return self.ddpg.control(tf_state).numpy()[0, 0]

    def train(self, simulator):
        pass




class PPO:
    def __init__(self, feature_size, min_value, max_value):
        self.process_pool = mp.Pool(mp.cpu_count())
        self.min_value = min_value
        self.max_value = max_value
        self.actor = tf.keras.Sequential([
            tf.keras.layers.Dense(300, activation=tf.nn.relu, input_shape=(feature_size,)),
            tf.keras.layers.Dense(300, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Actor")

    def train(self, simulator, init_step=0, episode=30, batch_size=128, gamma=0.95):
        def parallel_trajectory_collection(actor_model, count):
            def collect trajectory():
                simulator.reset()
                # reach initial state with enough history
                for i in range(init_step):
                    simulator.step(0.0)
                done = False
                rewards, states, actions = [], [], []

                while not(done):
                    state = tf.constant(simulator.get_concated_features(), dtype=tf.float32)
                    state = tf.reshape(state, (1, -1))
                    states.append(state)
                    action = np.clip((self.actor(state)).numpy(), self.min_value, self.max_value)
                    done, reward, _ = simulator.step(action[0, 0])
                    rewards.append(reward)
                    actions.append(action)

                #compute reward2go
                R=0.0
                corrected_rewards = []
                for r in rewards[::-1]:
                    R=r+gamma*R
                    corrected_rewards.append(R)
                corrected_rewards.reverse()
                return states,actions,



        for ep in tqdm(range(episode)):
            trajectories = self.process_pool.map(parallel_trajectory_collection,[(self.actor,batch_size // mp.cpu_count())]* mp.cpu_count)
