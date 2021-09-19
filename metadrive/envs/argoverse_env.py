import pathlib
import time
import pickle
from os import listdir
from typing import Union, Dict, AnyStr, Optional, Tuple
from collections import defaultdict
import numpy as np
import logging

from metadrive.component.map.argoverse_map import ArgoverseMap
from metadrive.envs.metadrive_env import MetaDriveEnv
from metadrive.manager.map_manager import MapManager
from metadrive.utils import is_win, ARGOVERSE_AGENT_ID

try:
    from argoverse.map_representation.map_api import ArgoverseMap as AGMap
except ImportError:
    pass

argoverse_city = "PIT"
argoverse_map_center = [2599.5505965123866, 1200.0214763629717]
argoverse_map_radius = 300
argoverse_spawn_lane_index = ('7903', '9713', 0)
argoverse_destination_node = "968"
argoverse_log_id = "c6911883-1843-3727-8eaa-41dc8cda8993"

logging.basicConfig(level=logging.INFO)
class ArgoverseMapManager(MapManager):

    def __init__(self, *args, **kwargs):
        super(ArgoverseMapManager, self).__init__(*args, **kwargs)
        self.ag_map = AGMap()
        self.cached_maps = {}

    def reset(self):
        if self.current_map is None:
            config = self.engine.global_config["map_config"]
            config_key = "%.1f-%.1f"%(config["center"][0], config['center'][1])
            if config_key in self.cached_maps:
                logging.info("use existing maps")
                map = self.cached_maps[config_key]
            else:
                logging.info("use new maps")
                map = self.spawn_object(ArgoverseMap, ag_map=self.ag_map,
                                        map_config=config,
                                        )
                self.cached_maps[config_key] = map
            self.engine.map_manager.load_map(map)
        else:
            print("Already have current map!")


class ArgoverseEnv(MetaDriveEnv):

    def __init__(self, log_id, *args, **kwargs):
        if log_id:
            root_path = pathlib.PurePosixPath(__file__).parent.parent if not is_win() else pathlib.Path(__file__).resolve(
            ).parent.parent
            data_path = root_path.joinpath("assets").joinpath("real_data").joinpath("test_parsed").joinpath("{}.pkl".format(log_id))
            with open(data_path, 'rb') as f:
                loaded_config = pickle.load(f)
                
            self.map_config = {
                "city": loaded_config["city"],
                "center": loaded_config["map_center"],
                "radius": argoverse_map_radius,
            }
            self.argoverse_config = {
                "agent_pos": {
                    "spawn_lane_index": loaded_config["agent_spawn_lane_index"],
                    "destination_node": loaded_config["agent_targ_node"]
                },
                "locate_info": loaded_config["locate_info"]
            }
        else:
            log_id = argoverse_log_id
            root_path = pathlib.PurePosixPath(__file__).parent.parent if not is_win() else pathlib.Path(__file__).resolve(
            ).parent.parent
            data_path = root_path.joinpath("assets").joinpath("real_data").joinpath("{}.pkl".format(log_id))
            with open(data_path, 'rb') as f:
                locate_info, _ = pickle.load(f)
            self.map_config = {
                "city": argoverse_city,
                "center": argoverse_map_center,
                "radius": argoverse_map_radius,
            }
            self.argoverse_config = {
                "agent_pos": {
                    "spawn_lane_index": argoverse_spawn_lane_index,
                    "destination_node": argoverse_destination_node,
                },
                "locate_info": locate_info
            }
        agent_info = list(self.argoverse_config["locate_info"][ARGOVERSE_AGENT_ID]["traj"].values())
        FREQ = 10
        self.agent_init_speed = (agent_info[1] - agent_info[0]) * FREQ
        self.argoverse_config["locate_info"].pop(ARGOVERSE_AGENT_ID)
        super(ArgoverseEnv, self).__init__(*args, **kwargs)
    
    def _post_process_config(self, config):
        config = super(ArgoverseEnv, self)._post_process_config(config)
        config["vehicle_config"]["spawn_lane_index"] = self.argoverse_config["agent_pos"]["spawn_lane_index"]
        config["vehicle_config"]["destination_node"] = self.argoverse_config["agent_pos"]["destination_node"]
        config.update({"real_data_config": {"locate_info": self.argoverse_config["locate_info"]}})
        config["traffic_density"] = 0.0  # Remove rule-based traffic flow
        config["map_config"].update(self.map_config)
        return config

    def setup_engine(self):
        super(ArgoverseEnv, self).setup_engine()
        from metadrive.manager.real_data_manager import RealDataManager
        self.engine.register_manager("real_data_manager", RealDataManager())
        self.engine.update_manager("map_manager", ArgoverseMapManager())

class ArgoverseMultiEnv(MetaDriveEnv):
    
    def __init__(self, config: dict = None):

        self.mode = config.pop("mode")
        super(ArgoverseMultiEnv, self).__init__(config)
        # check parsed training and testing data
        root_path = pathlib.PurePosixPath(__file__).parent.parent if not is_win() else pathlib.Path(__file__).resolve(
        ).parent.parent
        self.file_path = root_path.joinpath("assets").joinpath("real_data").joinpath("{}_parsed".format(self.mode))
        self.data_files = listdir(self.file_path)
        self.envs = [ArgoverseEnv(data_file.split(".")[0]) for data_file in self.data_files[self.start_seed:self.start_seed+self.env_num]]
        self.start_seed = 0

    def reset(self, episode_data: dict = None, force_seed: Union[None, int] = None):
        self._reset_global_seed(force_seed)
        self.current_env = self.envs[self.current_seed]
        self.current_env.reset()
        
    def step(self, actions: Union[np.ndarray, Dict[AnyStr, np.ndarray]]):
        self.current_env.step(actions)

class ArgoverseGeneralizationEnv(MetaDriveEnv):

    def __init__(self, config: dict = None):
        self.mode = config.pop("mode")
        # check parsed training and testing data
        super(ArgoverseGeneralizationEnv, self).__init__(config)
        root_path = pathlib.PurePosixPath(__file__).parent.parent if not is_win() else pathlib.Path(__file__).resolve(
        ).parent.parent
        self.file_path = root_path.joinpath("assets").joinpath("real_data").joinpath("{}_parsed".format(self.mode))
        self.agent_pos_path = root_path.joinpath("assets").joinpath("real_data").joinpath("agent_pos")
        self.data_files = sorted(listdir(self.file_path))
        for data_file in self.data_files:
            data_path = self.file_path.joinpath(data_file)


    def reset(self, episode_data: dict = None, force_seed: Union[None, int] = None):
        """
        Reset the env, scene can be restored and replayed by giving episode_data
        Reset the environment or load an episode from episode data to recover is
        setup map and agent parameters
        :param episode_data: Feed the episode data to replay an episode
        :param force_seed: The seed to set the env.
        :return: None
        """
        self.lazy_init()  # it only works the first time when reset() is called to avoid the error when render
        self._reset_global_seed(force_seed)
        self._reset_real_config()
        self.engine.reset()
        if self._top_down_renderer is not None:
            self._top_down_renderer.reset(self.current_map)

        self.dones = {agent_id: False for agent_id in self.vehicles.keys()}
        self.episode_steps = 0
        self.episode_rewards = defaultdict(float)
        self.episode_lengths = defaultdict(int)
        assert (len(self.vehicles) == self.num_agents) or (self.num_agents == -1)

        return self._get_reset_return()

    def setup_engine(self):
        super(ArgoverseGeneralizationEnv, self).setup_engine()
        from metadrive.manager.real_data_manager import RealDataManager
        self.engine.register_manager("real_data_manager", RealDataManager())
        self.engine.update_manager("map_manager", ArgoverseMapManager())

    def _reset_real_config(self):
        current_data_file = self.data_files[self.current_seed]
        # current_data_file = "b1ca08f1-24b0-3c39-ba4e-d5a92868462c.pkl" # infinite loop in navigation point searching
        # current_data_file = "70d2aea5-dbeb-333d-b21e-76a7f2f1ba1c.pkl" # delayed navigation point selection
        current_id = current_data_file.split(".")[0]
        print("map file: ", current_data_file)
        data_path = self.file_path.joinpath(current_data_file)
            
        with open(data_path, 'rb') as f:
            loaded_config = pickle.load(f)
        map_config = {
            "city": loaded_config["city"],
            "center": loaded_config["map_center"],
            "radius": argoverse_map_radius,
        }

        if current_id in listdir(self.agent_pos_path):
            with open(self.agent_pos_path.joinpath(current_id), 'r') as f:
                spawn_lane_index = eval(f.readline())
                targ_lane_index = eval(f.readline())
            agent_pos = {
                "spawn_lane_index": spawn_lane_index,
                "destination_node": targ_lane_index[0]
            }
        else:
            agent_pos = {
                "spawn_lane_index": loaded_config["agent_spawn_lane_index"],
                "destination_node": loaded_config["agent_targ_node"]
            }

        self.argoverse_config = {
            "locate_info": loaded_config["locate_info"]
        }
        agent_init_pos = self.argoverse_config["locate_info"][ARGOVERSE_AGENT_ID]["init_pos"]
        self.argoverse_config["locate_info"].pop(ARGOVERSE_AGENT_ID)

        config = self.engine.global_config
        config["vehicle_config"]["spawn_lane_index"] = agent_pos["spawn_lane_index"]
        config["vehicle_config"]["destination_node"] = agent_pos["destination_node"]
        config["vehicle_config"].update({"agent_init_pos": agent_init_pos})
        config.update({"real_data_config": {"locate_info": self.argoverse_config["locate_info"]}})
        config["traffic_density"] = 0.0  # Remove rule-based traffic flow
        config["map_config"].update(
            {
                "city": map_config["city"],
                "center": ArgoverseMap.metadrive_position([map_config["center"][0], -map_config["center"][1]]),
                "radius": map_config["radius"]
            }
        )
        
if __name__ == '__main__':
    # env = ArgoverseMultiEnv(dict(mode="train",environment_num=3, start_seed=15, use_render=False))
    env = ArgoverseGeneralizationEnv(dict(
            mode="test",
            environment_num=20, 
            start_seed=0,
            use_render=True,
            manual_control=True,
            disable_model_compression=True))
    while True:
        env.reset()
        env.vehicle.expert_takeover=True
        for _ in range(200):
            env.step([0., 0.])
            info = {}
            info["lane_index"] = env.vehicle.lane_index
            env.render(text=info)
            print(info)
    for i in range(10, 65):
        print(i)
        try:
            env = ArgoverseGeneralizationEnv(dict(mode="test",environment_num=1, start_seed=i, use_render=True, manual_control=True))
            env.reset()
            env.vehicle.expert_takeover=True
            for i in range(1, 200):
                o, r, d, info = env.step([0., 0.0])
        except (TypeError, AssertionError) as e:
            print("Assertion Failed!")
            raise e
        env.close()
