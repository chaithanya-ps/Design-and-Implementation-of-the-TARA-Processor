#!/usr/bin/env python3

import argparse
import sys

# --------------------------------------------------------------------------
# 1. Control-word fields  (name -> (lsb, width))   -- 25 bits in total
# --------------------------------------------------------------------------
FIELDS = {
    "STEP_RST":       (0, 1),
    "MAR_LOAD":       (1, 1),
    "MDR_LOAD":       (2, 1),
    "IR_LOAD":        (3, 1),
    "ACC_LOAD":       (4, 1),
    "REG_WE":         (5, 1),
    "MEM_READ":       (6, 1),
    "MEM_WRITE":      (7, 1),
    "STATUS_WE":      (8, 1),
    "IMM":            (9, 1),    # force IMM8 = 0xFF (LIH)
    "IMM_BIT_EXTEND": (10, 2),   # 00 zext imm8, 01 sext imm8, 10 imm8<<8, 11 zext imm5
    "ALU_OPCODE":     (12, 5),
    "BUS_SOURCE":     (17, 3),
    "PC_LOAD":        (20, 1),
    "PC_FETCH_EN":    (21, 1),   # 0: PC <- PC+2, 1: PC <- bus
    "HALT":           (22, 1),   # freezes the T-state counter
    "SPARE_1":        (23, 1),
    "SPARE_2":        (24, 1),
}
WORD_BITS = 25
WORD_HEX_DIGITS = (WORD_BITS + 3) // 4          # 7
ROM_WORDS = 2048

# Bus-source encoding (3 bits)
BUS_PC, BUS_MDR, BUS_IR, BUS_IMM, BUS_RF, BUS_ACC, BUS_RAM, BUS_IDLE = range(8)

# Extend modes
EXT_ZERO8, EXT_SIGN8, EXT_SHL8, EXT_ZERO5 = 0, 1, 2, 3

# ALU opcodes (identical to the instruction opcodes for the ALU instructions)
ALU = {"ADD": 9, "SUB": 10, "AND": 13, "OR": 14, "XOR": 15,
       "NOT": 16, "SHL": 17, "SHR": 18, "SLT": 19}

# Instruction opcodes (core set)
OPCODES = {
    "NOP": 0, "HLT": 1, "MOV": 2, "LIL": 3, "LIH": 4,
    "ADD": 9, "SUB": 10, "ADDI": 11, "AND": 13, "OR": 14, "XOR": 15,
    "NOT": 16, "SHL": 17, "SHR": 18, "SLT": 19,
}
NAME_OF = {v: k for k, v in OPCODES.items()}

# --------------------------------------------------------------------------
# 2. Packing helpers
# --------------------------------------------------------------------------
def pack(**kw):
    """Pack named fields into one integer. Unspecified fields take defaults."""
    word = 0
    for name, val in kw.items():
        lsb, width = FIELDS[name]          # KeyError => typo in a field name
        if not 0 <= val < (1 << width):
            raise ValueError(f"{name}={val} does not fit in {width} bit(s)")
        word |= val << lsb
    return word


def unpack(word):
    return {n: (word >> lsb) & ((1 << w) - 1) for n, (lsb, w) in FIELDS.items()}


# The safe word: bus idle, nothing loaded/written, return to T0.
SAFE = pack(BUS_SOURCE=BUS_IDLE, STEP_RST=1)

# --------------------------------------------------------------------------
# 3. Microcode
# --------------------------------------------------------------------------
FETCH = [
    # T0: MAR <- PC
    pack(BUS_SOURCE=BUS_PC, MAR_LOAD=1),
    # T1: MDR <- Mem[MAR]; PC <- PC + 2   (PC_FETCH_EN = 0 selects the +2 path)
    pack(BUS_SOURCE=BUS_RAM, MEM_READ=1, MDR_LOAD=1, PC_LOAD=1, PC_FETCH_EN=0),
    # T2: IR <- MDR
    pack(BUS_SOURCE=BUS_MDR, IR_LOAD=1),
]


def build_microcode(status_we=False):
    """Return {opcode: [word for T3, T4, ...]} for every implemented opcode.

    Execution begins at T3.  Missing states are filled with SAFE later.
    """
    sw = 1 if status_we else 0
    mc = {}

    mc[OPCODES["NOP"]] = [SAFE]                                    # T3
    mc[OPCODES["HLT"]] = [pack(BUS_SOURCE=BUS_IDLE, HALT=1)]       # T3, no STEP_RST

    # MOV Rd, Rs : ACC <- rs + 0  (A = QB = RA = rs, B = bus = imm5 = 0), then Rd <- ACC
    mc[OPCODES["MOV"]] = [
        pack(BUS_SOURCE=BUS_IMM, IMM_BIT_EXTEND=EXT_ZERO5, ALU_OPCODE=ALU["ADD"],
             ACC_LOAD=1, STATUS_WE=sw),
        pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
    ]

    # LIL Rd, imm8 : Rd <- zero-extended imm8
    mc[OPCODES["LIL"]] = [
        pack(BUS_SOURCE=BUS_IMM, IMM_BIT_EXTEND=EXT_ZERO8, REG_WE=1, STEP_RST=1),
    ]

    # Register-register ALU instructions:  ADD SUB AND OR XOR SLT
    #   T3: ACC <- RA op RB   (A = QB = RA, B = bus = QA = RB, see H1)
    #   T4: Rd  <- ACC
    for name in ("ADD", "SUB", "AND", "OR", "XOR", "SLT"):
        mc[OPCODES[name]] = [
            pack(BUS_SOURCE=BUS_RF, ALU_OPCODE=ALU[name], ACC_LOAD=1, STATUS_WE=sw),
            pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
        ]

    # NOT Rd, Rs : A = QB = RA = rs, ALU ignores B (bus carries QA, harmless)
    mc[OPCODES["NOT"]] = [
        pack(BUS_SOURCE=BUS_RF, ALU_OPCODE=ALU["NOT"], ACC_LOAD=1, STATUS_WE=sw),
        pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
    ]

    # ADDI Rd, imm8 : Rd <- Rd + sext(imm8).  A = QB = Rd (H1), B = bus = imm
    mc[OPCODES["ADDI"]] = [
        pack(BUS_SOURCE=BUS_IMM, IMM_BIT_EXTEND=EXT_SIGN8, ALU_OPCODE=ALU["ADD"],
             ACC_LOAD=1, STATUS_WE=sw),
        pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
    ]

    # SHL / SHR Rd, imm8 : Rd <- Rd shift imm5.  A = QB = Rd (H1), B = bus = imm5
    for name in ("SHL", "SHR"):
        mc[OPCODES[name]] = [
            pack(BUS_SOURCE=BUS_IMM, IMM_BIT_EXTEND=EXT_ZERO5,
                 ALU_OPCODE=ALU[name], ACC_LOAD=1, STATUS_WE=sw),
            pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
        ]

    # LIH Rd, imm8 : Rd <- (imm8 << 8) | (Rd & 0x00FF)   (read-modify-write)
    mc[OPCODES["LIH"]] = [
        # T3: ACC <- Rd AND 0x00FF     (IMM forces imm = 0xFF on the bus, A = Rd via H1)
        pack(BUS_SOURCE=BUS_IMM, IMM=1, IMM_BIT_EXTEND=EXT_ZERO8,
             ALU_OPCODE=ALU["AND"], ACC_LOAD=1),
        # T4: Rd <- ACC                (clears the high byte, keeps the low byte)
        pack(BUS_SOURCE=BUS_ACC, REG_WE=1),
        # T5: ACC <- (imm8 << 8) OR Rd
        pack(BUS_SOURCE=BUS_IMM, IMM_BIT_EXTEND=EXT_SHL8,
             ALU_OPCODE=ALU["OR"], ACC_LOAD=1),
        # T6: Rd <- ACC
        pack(BUS_SOURCE=BUS_ACC, REG_WE=1, STEP_RST=1),
    ]
    return mc


# --------------------------------------------------------------------------
# 4. ROM assembly
# --------------------------------------------------------------------------
def addr(z, n, op, t):
    return (z << 10) | (n << 9) | (op << 4) | t


def build_rom(mc):
    rom = [SAFE] * ROM_WORDS                      # every unspecified address is safe
    for z in (0, 1):
        for n in (0, 1):
            for op in range(32):
                # Fetch is common to every opcode: the IR still holds the previous
                # instruction while T0..T2 run, so all 32 opcodes need it.
                for t, w in enumerate(FETCH):
                    rom[addr(z, n, op, t)] = w
                for i, w in enumerate(mc.get(op, [])):
                    rom[addr(z, n, op, 3 + i)] = w
    return rom


# --------------------------------------------------------------------------
# 5. Consistency checks
# --------------------------------------------------------------------------
CONDITIONAL_OPCODES = set()        # TH6 will add BZ / BN here


def run_checks(rom, mc):
    log, ok = [], True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= passed
        log.append(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    # (1) at most one bus source, bus value legal, and loads have valid data
    bad = []
    for a, w in enumerate(rom):
        f = unpack(w)
        # BUS_SOURCE is one encoded field, so two simultaneous sources are structurally
        # impossible; we check that it is a defined encoding and that any word which
        # loads a register from the bus is not selecting the idle code.
        loads = f["MAR_LOAD"] or f["MDR_LOAD"] or f["IR_LOAD"] or f["REG_WE"] or f["ACC_LOAD"] \
            or (f["PC_LOAD"] and f["PC_FETCH_EN"])
        if loads and f["BUS_SOURCE"] == BUS_IDLE:
            bad.append(a)
        if f["BUS_SOURCE"] > 7:
            bad.append(a)
    report("one bus source per word and no load from an idle bus", not bad,
           f"{len(bad)} bad words" if bad else "")

    # (2) every implemented instruction asserts STEP_RST or HALT
    missing = []
    for op in mc:
        seen = False
        for t in range(3, 16):
            f = unpack(rom[addr(0, 0, op, t)])
            if f["STEP_RST"] or f["HALT"]:
                seen = True
                break
        if not seen:
            missing.append(NAME_OF.get(op, op))
    report("every implemented instruction reaches STEP_RST or HALT", not missing,
           ", ".join(map(str, missing)))

    # (3) MEM_READ and MEM_WRITE never together
    both = [a for a, w in enumerate(rom)
            if unpack(w)["MEM_READ"] and unpack(w)["MEM_WRITE"]]
    report("MEM_READ and MEM_WRITE never asserted together", not both)

    # (4) write enables never with no source data
    wr = [a for a, w in enumerate(rom)
          if (unpack(w)["REG_WE"] or unpack(w)["MEM_WRITE"]) and unpack(w)["BUS_SOURCE"] == BUS_IDLE]
    report("write enables never asserted without valid source data", not wr)

    # (5) conditional-branch words differ only in the condition bits
    diff = []
    for op in range(32):
        if op in CONDITIONAL_OPCODES:
            continue
        for t in range(16):
            ws = {rom[addr(z, n, op, t)] for z in (0, 1) for n in (0, 1)}
            if len(ws) != 1:
                diff.append((op, t))
    report("non-conditional opcodes ignore Z and N", not diff,
           f"{len(diff)} rows differ" if diff else "")

    # (6) undefined opcodes cannot modify architectural state
    leak = []
    for op in range(32):
        if op in mc:
            continue
        for t in range(3, 16):
            f = unpack(rom[addr(0, 0, op, t)])
            if f["REG_WE"] or f["MEM_WRITE"] or f["PC_LOAD"] or f["IR_LOAD"] or f["ACC_LOAD"] \
                    or f["MAR_LOAD"] or f["MDR_LOAD"]:
                leak.append((op, t))
    report("undefined opcodes modify no architectural state", not leak,
           f"{len(leak)} words" if leak else "")

    # (7) fetch rows identical for all 32 opcodes
    fetch_ok = all(rom[addr(z, n, op, t)] == FETCH[t]
                   for z in (0, 1) for n in (0, 1) for op in range(32) for t in range(3))
    report("fetch (T0-T2) present for every opcode and condition", fetch_ok)

    # (8) PC advances exactly once per instruction (only T1 has PC_LOAD)
    pcs = [(op, t) for op in range(32) for t in range(16)
           if unpack(rom[addr(0, 0, op, t)])["PC_LOAD"] and t != 1]
    report("PC_LOAD asserted only in T1 (PC +2 once per instruction)", not pcs,
           str(pcs[:3]) if pcs else "")

    # (9) every word fits in 25 bits
    wide = [a for a, w in enumerate(rom) if w >> WORD_BITS]
    report(f"all words fit in {WORD_BITS} bits", not wide)

    return ok, log


# --------------------------------------------------------------------------
# 6. Output
# --------------------------------------------------------------------------
def write_hex(rom, path):
    with open(path, "w") as fh:
        fh.write("v2.0 raw\n")
        for i in range(0, ROM_WORDS, 8):
            fh.write(" ".join(f"{w:0{WORD_HEX_DIGITS}x}" for w in rom[i:i + 8]) + "\n")


def dump(rom, name):
    op = OPCODES[name.upper()]
    print(f"{name.upper()}  opcode {op}  (Z=N=0 rows, base address 0x{addr(0, 0, op, 0):03X})")
    for t in range(8):
        w = rom[addr(0, 0, op, t)]
        nz = {k: v for k, v in unpack(w).items() if v}
        print(f"  T{t}  addr 0x{addr(0, 0, op, t):03X}  word {w:0{WORD_HEX_DIGITS}x}  {nz}")


def main():
    ap = argparse.ArgumentParser(description="TARA TH5 control ROM generator")
    ap.add_argument("-o", "--output", default="G06_th5_control_rom.hex")
    ap.add_argument("--dump", metavar="MNEMONIC", help="print the rows for one instruction")
    ap.add_argument("--status-we", action="store_true",
                    help="assert STATUS_WE at the ALU state (debug aid)")
    args = ap.parse_args()

    mc = build_microcode(status_we=args.status_we)
    rom = build_rom(mc)

    if args.dump:
        dump(rom, args.dump)
        return 0

    ok, log = run_checks(rom, mc)
    print("Consistency checks:")
    print("\n".join(log))
    if not ok:
        print("\nCHECKS FAILED -- no ROM file written.")
        return 1
    write_hex(rom, args.output)
    print(f"\nWrote {args.output}: {ROM_WORDS} words x {WORD_BITS} bits "
          f"({len(mc)} instructions implemented).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
