#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ClassiCube").resolve()

def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8-sig")

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")

def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f"patch anchor not found in {rel}: {old[:120]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"patch anchor not unique in {rel}: {old[:120]!r}")
    write(rel, text.replace(old, new, 1))

survival_h = r'''#ifndef CC_SURVIVAL_H
#define CC_SURVIVAL_H
#include "Core.h"
#include "BlockID.h"
CC_BEGIN_HEADER

#ifdef CC_SURVIVAL_TEST
struct IGameComponent;
extern struct IGameComponent Survival_Component;

cc_bool Survival_Active(void);
cc_bool Survival_CanPlace(BlockID block);
void Survival_OnPlace(BlockID block);
void Survival_OnDelete(BlockID block);
int Survival_GetHealth(void);
int Survival_GetSelectedCount(void);
#endif

CC_END_HEADER
#endif
'''

survival_c = r'''#include "Survival.h"

#ifdef CC_SURVIVAL_TEST
#include "Game.h"
#include "Inventory.h"
#include "Server.h"
#include "World.h"
#include "Entity.h"
#include "Chat.h"
#include "Event.h"
#include "String_.h"
#include "ExtMath.h"

#define SURVIVAL_MAX_HEALTH 20
#define SURVIVAL_MAX_STACK  99

static cc_uint8 counts[INVENTORY_HOTBARS * INVENTORY_BLOCKS_PER_HOTBAR];
static int health = SURVIVAL_MAX_HEALTH;
static cc_bool wasOnGround;
static float fallPeakY;
static struct ScheduledTask2 survivalTask;

static int SelectedSlot(void) {
    return Inventory.Offset + Inventory.SelectedIndex;
}

cc_bool Survival_Active(void) {
    return Server.IsSinglePlayer && World.Loaded;
}

int Survival_GetHealth(void) { return health; }

int Survival_GetSelectedCount(void) {
    int slot = SelectedSlot();
    return slot >= 0 && slot < Array_Elems(counts) ? counts[slot] : 0;
}

static void UpdateStatus(void) {
    cc_string msg;
    char buffer[STRING_SIZE];
    int count = Survival_GetSelectedCount();
    int maxHealth = SURVIVAL_MAX_HEALTH;

    String_InitArray(msg, buffer);
    String_Format3(&msg, "&cHP %i/%i  &eStack %i", &health, &maxHealth, &count);
    Chat_AddOf(&msg, MSG_TYPE_STATUS_1);
}

static void ClearInventory(void) {
    int i;
    for (i = 0; i < Array_Elems(Inventory.Table); i++) Inventory.Table[i] = BLOCK_AIR;
    for (i = 0; i < Array_Elems(counts); i++) counts[i] = 0;

    /* Match the old experimental Survival Test client: 10 TNT in the last slot. */
    Inventory.Offset = 0;
    Inventory.SelectedIndex = 0;
    Inventory.Table[INVENTORY_BLOCKS_PER_HOTBAR - 1] = BLOCK_TNT;
    counts[INVENTORY_BLOCKS_PER_HOTBAR - 1] = 10;
}

static int RandRange(int minValue, int maxValue) {
    cc_uint32 v = (cc_uint32)(Game.Time * 1000003.0);
    v ^= v << 13; v ^= v >> 17; v ^= v << 5;
    return minValue + (int)(v % (cc_uint32)(maxValue - minValue + 1));
}

static void AddItem(BlockID block, int count) {
    int i, slot = -1, offset = Inventory.Offset;

    for (i = 0; i < INVENTORY_BLOCKS_PER_HOTBAR; i++) {
        if (Inventory.Table[offset + i] == block && counts[offset + i] < SURVIVAL_MAX_STACK) {
            slot = offset + i; break;
        }
    }
    if (slot == -1) {
        for (i = 0; i < INVENTORY_BLOCKS_PER_HOTBAR; i++) {
            if (Inventory.Table[offset + i] == BLOCK_AIR || counts[offset + i] == 0) {
                slot = offset + i; break;
            }
        }
    }
    if (slot == -1) {
        Chat_AddRaw("&cInventory full");
        return;
    }

    Inventory.Table[slot] = block;
    counts[slot] = min(SURVIVAL_MAX_STACK, counts[slot] + count);
    UpdateStatus();
}

void Survival_OnDelete(BlockID old) {
    BlockID drop = old;
    int amount = 1;

    if (!Survival_Active()) return;

    switch (old) {
    case BLOCK_GRASS:    drop = BLOCK_DIRT;   break;
    case BLOCK_STONE:    drop = BLOCK_COBBLE; break;
    case BLOCK_LOG:      drop = BLOCK_WOOD; amount = RandRange(3, 5); break;
    case BLOCK_COAL_ORE: drop = BLOCK_SLAB; amount = RandRange(1, 3); break;
    case BLOCK_IRON_ORE: drop = BLOCK_IRON; break;
    case BLOCK_GOLD_ORE: drop = BLOCK_GOLD; break;
    case BLOCK_LEAVES:
        if (RandRange(1, 15) != 1) return;
        drop = BLOCK_SAPLING;
        break;
    case BLOCK_BEDROCK:
    case BLOCK_AIR:
    case BLOCK_WATER:
    case BLOCK_STILL_WATER:
    case BLOCK_LAVA:
    case BLOCK_STILL_LAVA:
        return;
    }
    AddItem(drop, amount);
}

cc_bool Survival_CanPlace(BlockID block) {
    int slot;
    if (!Survival_Active()) return true;
    if (block == BLOCK_AIR) return false;

    slot = SelectedSlot();
    if (slot < 0 || slot >= Array_Elems(counts)) return false;
    if (counts[slot] == 0 || Inventory.Table[slot] != block) {
        UpdateStatus();
        return false;
    }
    return true;
}

void Survival_OnPlace(BlockID block) {
    int slot;
    if (!Survival_Active()) return;

    slot = SelectedSlot();
    if (slot < 0 || slot >= Array_Elems(counts)) return;
    if (counts[slot] == 0 || Inventory.Table[slot] != block) return;

    counts[slot]--;
    if (!counts[slot]) {
        Inventory.Table[slot] = BLOCK_AIR;
        Event_RaiseVoid(&UserEvents.HeldBlockChanged);
    }
    UpdateStatus();
}

static void RespawnPlayer(void) {
    struct LocalPlayer* p = &LocalPlayer_Instances[0];
    struct LocationUpdate update;

    update.pos   = p->Spawn;
    update.yaw   = p->SpawnYaw;
    update.pitch = p->SpawnPitch;
    update.rotX  = 0.0f;
    update.rotZ  = 0.0f;
    update.flags = LU_HAS_POS | LU_HAS_YAW | LU_HAS_PITCH | LU_POS_ABSOLUTE_INSTANT;

    p->Base.VTABLE->SetLocation(&p->Base, &update);
    p->Base.Velocity.x = 0.0f;
    p->Base.Velocity.y = 0.0f;
    p->Base.Velocity.z = 0.0f;
}

static void Damage(int amount) {
    if (amount <= 0) return;
    health -= amount;
    if (health > 0) {
        UpdateStatus();
        return;
    }

    Chat_AddRaw("&cYou died! Respawning...");
    health = SURVIVAL_MAX_HEALTH;
    ClearInventory();
    RespawnPlayer();
    wasOnGround = true;
    fallPeakY = LocalPlayer_Instances[0].Base.Position.y;
    UpdateStatus();
}

static cc_bool Survival_Tick(struct ScheduledTask2* task) {
    struct Entity* e;
    float dist;
    int damage;

    (void)task;
    if (!Survival_Active()) return true;

    e = &LocalPlayer_Instances[0].Base;
    if (e->OnGround) {
        if (!wasOnGround) {
            dist = fallPeakY - e->Position.y;
            if (dist > 3.0f && !Entity_TouchesAnyWater(e)) {
                damage = (int)(dist - 3.0f);
                Damage(damage);
            }
        }
        fallPeakY = e->Position.y;
    } else {
        fallPeakY = max(fallPeakY, e->Position.y);
    }
    wasOnGround = e->OnGround;
    return true;
}

static void Survival_Init(void) {
    survivalTask.interval = 0.05f;
    survivalTask.callback = Survival_Tick;
    ScheduledTask2_Add(&survivalTask);
}

static void Survival_Reset(void) {
    health = SURVIVAL_MAX_HEALTH;
    wasOnGround = true;
    fallPeakY = 0.0f;
}

static void Survival_OnNewMapLoaded(void) {
    struct Entity* e;
    if (!Server.IsSinglePlayer) return;

    ClearInventory();
    health = SURVIVAL_MAX_HEALTH;
    e = &LocalPlayer_Instances[0].Base;
    wasOnGround = e->OnGround;
    fallPeakY = e->Position.y;
    Chat_AddRaw("&aSurvival Test enabled");
    UpdateStatus();
}

struct IGameComponent Survival_Component = {
    Survival_Init, NULL, Survival_Reset, NULL, Survival_OnNewMapLoaded
};
#endif
'''

write("src/Survival.h", survival_h)
write("src/Survival.c", survival_c)

replace_once(
    "src/Game.c",
    '#include "EntityRenderers.h"\n',
    '#include "EntityRenderers.h"\n#ifdef CC_SURVIVAL_TEST\n#include "Survival.h"\n#endif\n'
)
replace_once(
    "src/Game.c",
    '\tGame_AddComponent(&Entities_Component);\n\n\tGame_AddComponent(&Gui_Component);',
    '\tGame_AddComponent(&Entities_Component);\n#ifdef CC_SURVIVAL_TEST\n\tGame_AddComponent(&Survival_Component);\n#endif\n\n\tGame_AddComponent(&Gui_Component);'
)

replace_once(
    "src/InputHandler.c",
    '#include "Picking.h"\n',
    '#include "Picking.h"\n#ifdef CC_SURVIVAL_TEST\n#include "Survival.h"\n#endif\n'
)
replace_once(
    "src/InputHandler.c",
    '\tGame_ChangeBlock(pos.x, pos.y, pos.z, BLOCK_AIR);\n\tEvent_RaiseBlock(&UserEvents.BlockChanged, pos, old, BLOCK_AIR);\n}',
    '\tGame_ChangeBlock(pos.x, pos.y, pos.z, BLOCK_AIR);\n\tEvent_RaiseBlock(&UserEvents.BlockChanged, pos, old, BLOCK_AIR);\n#ifdef CC_SURVIVAL_TEST\n\tif (Survival_Active()) Survival_OnDelete(old);\n#endif\n}'
)
replace_once(
    "src/InputHandler.c",
    '\tblock = Inventory_SelectedBlock;\n\tif (AutoRotate_Enabled) block = AutoRotate_RotateBlock(block);\n\n\tif (Game_CanPick(old) || !Blocks.CanPlace[block]) return;',
    '\tblock = Inventory_SelectedBlock;\n\tif (AutoRotate_Enabled) block = AutoRotate_RotateBlock(block);\n#ifdef CC_SURVIVAL_TEST\n\tif (Survival_Active() && !Survival_CanPlace(block)) return;\n#endif\n\n\tif (Game_CanPick(old) || !Blocks.CanPlace[block]) return;'
)
replace_once(
    "src/InputHandler.c",
    '\tGame_ChangeBlock(pos.x, pos.y, pos.z, block);\n\tEvent_RaiseBlock(&UserEvents.BlockChanged, pos, old, block);\n}',
    '\tGame_ChangeBlock(pos.x, pos.y, pos.z, block);\n\tEvent_RaiseBlock(&UserEvents.BlockChanged, pos, old, block);\n#ifdef CC_SURVIVAL_TEST\n\tif (Survival_Active()) Survival_OnPlace(block);\n#endif\n}'
)
replace_once(
    "src/InputHandler.c",
    'static void InputHandler_PickBlock(void) {\n\tIVec3 pos;',
    'static void InputHandler_PickBlock(void) {\n#ifdef CC_SURVIVAL_TEST\n\tif (Survival_Active()) return;\n#endif\n\tIVec3 pos;'
)

replace_once(
    "misc/3ds/Makefile",
    '\t\t\t-D__3DS__ -DPLAT_3DS\n',
    '\t\t\t-D__3DS__ -DPLAT_3DS -DCC_SURVIVAL_TEST\n'
)

print("Applied ClassiCube 3DS Survival Test patch")
