from pikocoin.config import NodeConfig
from pikocoin.node import run_node


if __name__ == "__main__":
    run_node(NodeConfig.from_env())
