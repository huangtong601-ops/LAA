# -*- coding: utf-8 -*-
"""LAA(MFAAvalonia) agent：注册竞技场等自定义动作。
由 interface.json 的 agent 配置拉起；socket_id 由 MaaFramework 传入。
"""
import sys

from maa.agent.agent_server import AgentServer
from maa.toolkit import Toolkit

from arena_loop import ArenaLoop
from base_order_flow import BaseOrderFlow
from chip_filter_flow import ChipFilterFlow
from startgame_flow import StartGameFlow
from weekly_complete import WeeklyFlow

AgentServer.custom_action("arena_loop")(ArenaLoop)
AgentServer.custom_action("base_order_flow")(BaseOrderFlow)
AgentServer.custom_action("chip_filter_flow")(ChipFilterFlow)
AgentServer.custom_action("startgame")(StartGameFlow)
AgentServer.custom_action("weekly_flow")(WeeklyFlow)


def main():
    Toolkit.init_option("./")
    if len(sys.argv) < 2:
        print("Usage: python main.py <socket_id>", file=sys.stderr)
        sys.exit(1)
    socket_id = sys.argv[-1]
    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
