from gym_novel_gridworlds2.utils.json_parser import import_module, load_json
from gym_novel_gridworlds2.contrib.polycraft.states import PolycraftState
from gym_novel_gridworlds2.contrib.polycraft.utils.map_utils import getBlockInFront
from gym_novel_gridworlds2.state.dynamic import Dynamic
from gym_novel_gridworlds2.contrib.polycraft.objects.polycraft_entity import PolycraftEntity
import os
import numpy as np

PDDL_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "pddl_template.pddl")
PDDL_PROBLEM_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "pddl_problem_template.pddl")
with open(PDDL_TEMPLATE_PATH, 'r') as f:
    PDDL_TEMPLATE = f.read()
with open(PDDL_PROBLEM_TEMPLATE_PATH, 'r') as f:
    PDDL_PROBLEM_TEMPLATE = f.read()

def generate_pddl(ng2_config, state: PolycraftState, dynamics: Dynamic):
    pddl_domain = PDDL_TEMPLATE
    pddl_problem = PDDL_PROBLEM_TEMPLATE

    # generate the object types and the entities
    object_types = generate_obj_types(ng2_config)
    entities = get_entities(ng2_config)
    obj_types_pddl_content = "\n".join(
        [f"    {obj_type} - {property}" for obj_type, property in object_types]
    )
    pddl_domain = pddl_domain.replace(";{{object_types}}", obj_types_pddl_content)
    all_objs = [f"{obj_type} - {obj_type}" for obj_type ,_ in object_types] + [f"{entity} - {t}" for entity, t in entities]
    pddl_problem = pddl_problem.replace(";{{objects}}", "\n        ".join(all_objs))
    
    # actions
    actions = generate_actions(ng2_config)
    pddl_domain = pddl_domain.replace(";{{additional_actions}}", "\n\n".join(actions))

    # initial state
    initial_state = generate_initial_state(ng2_config, state, dynamics)
    pddl_problem = pddl_problem.replace(";{{init}}", "\n        ".join(initial_state))

    return pddl_domain, pddl_problem


def get_entities(ng2_config):
    entities = []
    for entity_nickname, entity in ng2_config["entities"].items():
        entities.append((f"entity_{entity['id']}", entity["type"]))
    return entities


def generate_initial_state(ng2_config, state: PolycraftState, dynamics: Dynamic):
    entity_id = ng2_config["entities"]["main_1"]["id"]
    main_entity: PolycraftEntity = state.get_entity_by_id(entity_id)
    object_types = generate_obj_types(ng2_config)

    ## generated objects
    objs_world = {"air": 0}
    for row in state._map:
        for cell in row:
            if cell is None:
                objs_world["air"] += 1
                continue

            # there's something at the cell
            obj_type, info = cell.get_map_rep()
            if obj_type in objs_world:
                objs_world[obj_type] += 1
            else:
                objs_world[obj_type] = 1

    # inventory
    objs_inventory = main_entity.inventory

    # initial state
    init_state = []
    for item, count in objs_world.items():
        init_state.append(f"(= (world {item}) {count})")
    for item, count in objs_inventory.items():
        init_state.append(f"(= (inventory {item}) {count})")
    # set counter to 0 for every object in the world
    for item, property in object_types:
        if item not in objs_inventory:
            init_state.append(f"(= (inventory {item}) 0)")

    
    # facing / holding
    main_facing = getBlockInFront(main_entity, state)
    init_state.append(f"(facing {main_facing['name']} one)")
    init_state.append(f"(holding {main_entity.selectedItem or 'air'})")
    return init_state
        


def generate_actions(ng2_config):
    # generate the actions
    actions = []

    ## craft
    for recipe_name, recipe in ng2_config["recipes"].items():
        # header
        action = f"(:action craft_{recipe_name}\n"
        action += "    :parameters ()\n"

        
        # preconditions, input
        action += "    :precondition (and\n"
        
        ## check if the player is facing a crafting table if needed.
        if len(recipe["input"]) > 4:
            action += "        (facing crafting_table one)\n"
        
        ## check if the player has enough items
        input_dict = {}
        for obj in recipe["input"]:
            if obj in input_dict:
                input_dict[obj] += 1
            else:
                input_dict[obj] = 1
        for key, count in input_dict.items():
            if key != "0":
                action += f"        (>= ( inventory {key}) {count})\n"
        action += "    )\n"
        
        # effect, output
        action += "    :effect (and\n"
        ## remove the input items
        for key, count in input_dict.items():
            if key != "0":
                action += f"        (decrease ( inventory {key}) {count})\n"
        for item, count in recipe["output"].items():
            action += f"        (increase ( inventory {item}) {count})\n"
        action += "    )\n"
        action += ")\n"
        actions.append(action)

    ## trade
    for trade_name, trade in ng2_config["trades"].items():
        # header
        action = f"(:action trade_{trade_name}\n"
        action += "    :parameters ()\n"

        
        # preconditions, input
        action += "    :precondition (and\n"
        
        ## check if facing the right entity
        action += f"        (facing entity_{ trade['trader'][0] } one)\n"
        
        ## check if the player has enough items
        for key, count in trade["input"].items():
            action += f"        (>= ( inventory {key}) {count})\n"
        action += "    )\n"
        
        # effect, output
        action += "    :effect (and\n"
        ## remove the input items
        for key, count in trade["input"].items():
            if key != "0":
                action += f"        (decrease ( inventory {key}) {count})\n"
        for item, count in trade["output"].items():
            action += f"        (increase ( inventory {item}) {count})\n"
        action += "    )\n"
        action += ")\n"
        actions.append(action)
    
    return actions


def generate_obj_types(ng2_config):
    object_types = []
    objs_set = set()

    # add explicitly defined object types
    for obj_type, info in ng2_config["object_types"].items():
        if obj_type == "default":
            continue
        if type(info) == str:
            Module = import_module(info)
        else:
            Module = import_module(info["module"])
        
        # append object according to its type
        if obj_type not in objs_set:
            obj_breakable_holding = getattr(Module, "breakable_holding", None)

            if getattr(Module, "breakable", False):
                object_types.append((obj_type, "hand_breakable"))
            elif type(obj_breakable_holding) == list and len(obj_breakable_holding) > 0:
                # assume it's pickaxe breakable if it's breakable while holding something
                object_types.append((obj_type, "pickaxe_breakable"))
            elif Module.placeable:
                object_types.append((obj_type, "placeable"))
            else:
                object_types.append((obj_type, "physobj"))
            objs_set.add(obj_type)
    
    # add extra object types in the world
    ## generated objects
    for obj_type in ng2_config["objects"]:
        if obj_type not in objs_set:
            object_types.append((obj_type, "placeable"))
            objs_set.add(obj_type)
    
    ## output of the recipes and crafts
    for recipe in ng2_config["recipes"].values():
        for obj in recipe['input']:
            if obj not in objs_set and obj != "0":
                object_types.append((obj, "physobj"))
                objs_set.add(obj)
        for obj in recipe['output']:
            if obj not in objs_set:
                object_types.append((obj, "physobj"))
                objs_set.add(obj)
    
    for trade in ng2_config["trades"].values():
        for obj in trade['input']:
            if obj not in objs_set:
                object_types.append((obj, "physobj"))
                objs_set.add(obj)
        for obj in trade['output']:
            if obj not in objs_set:
                object_types.append((obj, "physobj"))
                objs_set.add(obj)
    
    ## extra objects custom defined
    object_types.append(("blue_key", "physobj"))
    return object_types
