import tensorflow as tf
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
            return self.ppo.control(tf_state).numpy()[0, 0]

    def train(self, simulator):
        self.ppo.train(simulator,)


def parallel_trajectory_collection(simulator,actor_model, count, min_value, max_value, sigma=0.0):
    def collect_trajectory():
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
            act = (actor_model(state)).numpy()
            act+= np.random.normal(loc=0.0, scale=sigma,size =act.shape)
            action = np.clip(act, min_value, max_value)
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
        return states,actions, corrected_rewards
    return [collect_trajectory() for i in range(count)]


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
        self.critic = tf.keras.Sequential([
            tf.keras.layers.Dense(300, activation=tf.nn.relu, input_shape=(feature_size,)),
            tf.keras.layers.Dense(300, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Critic")

    def train(self, simulator, init_step=0, episode=30, batch_size=128, gamma=0.95, grad_step=3, epsilon=0.1, exploration_decay=0.99):


        sigma=0.1
        optimizer = tf.keras.optimizers.Adam()
        for ep in range(episode):
            self.process_pool.map(parallel_trajectory_collection,[(simulator,simulator,batch_size // mp.cpu_count(),self.min_value,self.max_value, sigma)])
            trajectories = self.process_pool.map(parallel_trajectory_collection,[(simulator,self.actor,batch_size // mp.cpu_count(),self.min_value,self.max_value, sigma)] * mp.cpu_count())
            states = [traject[0] for traject in trajectories]
            actions = [traject[1] for traject in trajectories]
            rewards = [traject[2] for traject in trajectories]
            pi_old = self.actor(states)
            for step in range(grad_step):
                with tf.GradientTape() as tape:
                    pi_new =self.actor(states)
                    value = self.critic(states)
                    ratio = tf.math.exp((2*actions*(pi_new-pi_old)+tf.math.square(pi_old)-tf.math.square(pi_new))/(2*sigma*sigma))
                    clipped_ratio = tf.clip_by_value(ratio,1-epsilon,1+epsilon,name='PPO_Clip')
                    advantage = rewards - value
                    loss_actor = - tf.minimum(ratio*advantage,clipped_ratio*advantage)
                    loss_critic = tf.keras.losses.MSE(rewards,value)
                grad_actor = tape.gradient(loss_actor, self.actor.trainable_variables)
                grad_critic = tape.gradient(loss_critic, self.critic.trainable_variables)
                optimizer.apply_gradients(zip(grad_actor, self.actor.trainable_variables))
                optimizer.apply_gradients(zip(grad_critic, self.critic.trainable_variables))
            sigma = sigma*exploration_decay


    def control(self,state):
        action = np.clip(self.actor(state), self.min_value, self.max_value)
        return action