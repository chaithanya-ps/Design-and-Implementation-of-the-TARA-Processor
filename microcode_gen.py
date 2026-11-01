#!/usr/bin/env python3
"""
Control-ROM generator for the TARA CPU (16-bit control word).

Control word layout (matches tara_control's splitter, LSB first):
  bit  0      STEP_RST
  bit  1      MAR_LOAD
  bit  2      MDR_LOAD
  bit  3      ACC_LOAD
  bit  4      REG_WE
  bit  5      MEM_READ
  bit  6      MEM_WRITE
  bit  7      STATUS_WE
  bit  8      IMM            (force IMM8 = 0xFF)
  bits 9-10   IMM_BIT_EXTEND (0 zero-ext, 1 sign-ext imm8, 2 imm8<<8, 3 sign-ext imm5)
  bits 11-13  BUS_SOURCE     (0 PC, 1 MDR, 2 IR/REL, 3 IMM, 4 REG, 5 ACC, 6 RAM, 7 off)
  bit  14     PC_LOAD
  bit  15     HALT

ROM address (11 bits) = Z<<10 | N<<9 | opcode<<4 | tstate

Signals NOT in the ROM any more (generated in taracpu):
  IR_LOAD = (T==2)      PC_FETCH_EN = (T!=1)
  BYTE_OP = (op in {7,8}) & (T==6)
  ALU_OPCODE = IR opcode, except op4 (LIH): T3->13 (AND), other T->14 (OR);
               op20/21 (BZ/BN, format F5): T3->13 (AND);
               op26 (POP): T3->13 (AND), other T->10 (SUB)

Usage:
  python3 gen_control_rom.py                   # writes control_rom.hex  (Logisim "v2.0 raw")
  python3 gen_control_rom.py in.circ out.circ  # also patches the ROM contents into a .circ
"""
import sys, re

# ---- field encoders -------------------------------------------------------
STEP_RST, MAR, MDR, ACC, REG_WE, MEM_R, MEM_W, STAT, IMM = (1 << i for i in range(9))
PC_LOAD, HALT = 1 << 14, 1 << 15
def EXT(v): return v << 9
def BUS(v): return v << 11
PC, MDRB, IRB, IMMB, REG, ACCB, RAM, OFF = range(8)      # BUS_SOURCE values

IDLE = STEP_RST | BUS(OFF)         # default/unused T-state: BUS_SOURCE=OFF (0), STEP_RST=1 (reset T-state counter to T0)

# Instruction fetch microsequence (T0-T2), shared by all 32 opcodes:
FETCH = [
    MAR | BUS(PC),                     # T0: BUS<-PC, MAR_LOAD=1                | MAR <- PC
    MDR | MEM_R | PC_LOAD | BUS(RAM),  # T1: BUS<-RAM[MAR>>1], MDR_LOAD=1,      | MDR <- RAM[MAR>>1], PC <- PC + 2
                                       #     MEM_READ=1, PC_LOAD=1 (PC_FETCH_EN=0 at T1)
    BUS(MDRB),                         # T2: BUS<-MDR (IR_LOAD=1 at T2)         | IR <- MDR
]

# ---- microcode (rows from T3 on). Z/N-dependent ops use a function -------
def op_rows(op, z, n):
    """Return the list of control words for T3.. of this opcode (z,n = flags)."""
    # Shared final write-back step: drive ACC onto bus, write to R[rd], reset T-state counter
    ADDI_END = [STEP_RST | REG_WE | BUS(ACCB)]  # BUS<-ACC, REG_WE=1, STEP_RST=1 | R[rd] <- ACC, T <- 0

    if op == 0:                                 # NOP (0x00)
        return []                               # T3 falls through to IDLE: STEP_RST=1, BUS<-0 | T <- 0

    if op == 1:                                 # HLT (0x01)
        return [
            HALT | BUS(OFF),                    # T3: HALT=1, BUS_SOURCE=OFF     | Freeze T-state and cycle counters
        ]

    if op == 2:                                 
        return [
            STEP_RST | REG_WE | BUS(REG)        # MOV: Rd <- R[RA] via port A
        ]                            
  
    if op == 3:                                 # LDI rd, imm8 (0x03)
        return [
            STEP_RST | REG_WE | BUS(IMMB),      # T3: BUS<-zext(imm8), REG_WE=1, STEP_RST=1    | R[rd] <- zext(imm8), T <- 0
        ]

    if op == 4:                                 # LDIH rd, imm8 (0x04)
        return [
            ACC | IMM | BUS(IMMB),              # T3: IMM=1, EXT=0 (0x00FF), BUS<-IMM, ACC_LOAD=1 (ALU_OP=13 AND) | ACC <- R[rd] & 0x00FF
            REG_WE | BUS(ACCB),                 # T4: BUS<-ACC, REG_WE=1                                          | R[rd] <- ACC
            ACC | EXT(2) | BUS(IMMB),           # T5: EXT=2 (imm8<<8), BUS<-IMM, ACC_LOAD=1 (ALU_OP=14 OR)        | ACC <- R[rd] | (imm8 << 8)
            STEP_RST | REG_WE | BUS(ACCB),      # T6: BUS<-ACC, REG_WE=1, STEP_RST=1                              | R[rd] <- ACC, T <- 0
        ]

    if op == 5:                                 # LDW rd, [ra, off5] (0x05)
        return [
            ACC | EXT(3) | BUS(IMMB),           # T3: BUS<-sext(off5), ACC_LOAD=1 (ALU_OP=ADD) | ACC <- R[ra] + sext(off5)
            MAR | BUS(ACCB),                    # T4: BUS<-ACC, MAR_LOAD=1                     | MAR <- ACC
            MDR | MEM_R | BUS(RAM),             # T5: BUS<-RAM[MAR>>1], MEM_READ=1, MDR_LOAD=1 | MDR <- RAM[MAR>>1]
            STEP_RST | REG_WE | BUS(MDRB),      # T6: BUS<-MDR, REG_WE=1, STEP_RST=1           | R[rd] <- MDR, T <- 0
        ]

    if op == 6:                                 # STW rd, [ra, off5] (0x06)
        return [
            ACC | EXT(3) | BUS(IMMB),           # T3: BUS<-sext(off5), ACC_LOAD=1 (ALU_OP=ADD) | ACC <- R[ra] + sext(off5)
            MAR | BUS(ACCB),                    # T4: BUS<-ACC, MAR_LOAD=1                     | MAR <- ACC
            MDR | BUS(REG),                     # T5: BUS<-R[rd] (REG_A=RD), MDR_LOAD=1        | MDR <- R[rd]
            STEP_RST | MEM_W | BUS(MDRB),       # T6: BUS<-MDR, MEM_WRITE=1, STEP_RST=1        | RAM[MAR>>1] <- MDR, T <- 0
        ]

    if op == 7:                                 # LDB rd, [ra, off5] (0x07)
        return [
            ACC | EXT(3) | BUS(IMMB),           # T3: BUS<-sext(off5), ACC_LOAD=1 (ALU_OP=ADD) | ACC <- R[ra] + sext(off5)
            MAR | BUS(ACCB),                    # T4: BUS<-ACC, MAR_LOAD=1                     | MAR <- ACC
            MDR | MEM_R | BUS(RAM),             # T5: BUS<-RAM[MAR>>1], MEM_READ=1, MDR_LOAD=1 | MDR <- RAM[MAR>>1] (full word, BYTE_OP=0)
            STEP_RST | REG_WE | BUS(MDRB),      # T6: BUS<-MDR (BYTE_OP=1 at T6), REG_WE=1,    | R[rd] <- zext(MDR_byte[MAR[0]]), T <- 0
                                                #     STEP_RST=1
        ]

    if op == 8:                                 # STB rd, [ra, off5] (0x08)
        return [
            ACC | EXT(3) | BUS(IMMB),           # T3: BUS<-sext(off5), ACC_LOAD=1 (ALU_OP=ADD) | ACC <- R[ra] + sext(off5)
            MAR | BUS(ACCB),                    # T4: BUS<-ACC, MAR_LOAD=1                     | MAR <- ACC
            MDR | MEM_R | BUS(RAM),             # T5: BUS<-RAM[MAR>>1], MEM_READ=1, MDR_LOAD=1 | MDR <- RAM[MAR>>1] (read full word, BYTE_OP=0)
            MDR | BUS(REG),                     # T6: BUS<-R[rd] (BYTE_OP=1 at T6), MDR_LOAD=1 | MDR_byte[MAR[0]] <- R[rd][7:0] (merge byte lane)
            STEP_RST | MEM_W | BUS(MDRB),       # T7: BUS<-MDR (BYTE_OP=0), MEM_WRITE=1,       | RAM[MAR>>1] <- MDR, T <- 0
                                                #     STEP_RST=1
        ]

    if op in (9, 10, 13, 14, 15, 16, 19):       # R-type ALU: ADD(9), SUB(10), AND(13), OR(14), XOR(15), NOT(16), SLT(19)
        return [
            ACC | BUS(REG),                     # T3: BUS<-R[rb] (REG_A=RB), ACC_LOAD=1 (ALU_OP=op) | ACC <- R[ra] <op> R[rb] (or ~R[ra])
        ] + ADDI_END                            # T4: BUS<-ACC, REG_WE=1, STEP_RST=1                | R[rd] <- ACC, T <- 0

    if op == 11:                                # ADDI rd, imm8 (0x0B)
        return [
            ACC | EXT(1) | BUS(IMMB),           # T3: BUS<-sext(imm8), ACC_LOAD=1 (ALU_OP=ADD, REG_B=RD) | ACC <- R[rd] + sext(imm8)
        ] + ADDI_END                            # T4: BUS<-ACC, REG_WE=1, STEP_RST=1                     | R[rd] <- ACC, T <- 0

    if op in (17, 18):                          # Shift by imm5: SLL(17), SRA(18)
        return [
            ACC | EXT(3) | BUS(IMMB),           # T3: BUS<-sext(imm5), ACC_LOAD=1 (ALU_OP=17/18) | ACC <- R[ra] << imm5 (or >> imm5)
        ] + ADDI_END                            # T4: BUS<-ACC, REG_WE=1, STEP_RST=1             | R[rd] <- ACC, T <- 0

    if op in (20, 21):                          # Conditional branch: BZ(20), BN(21)
        # T3: IMM=1, EXT=1 (0xFFFF), BUS<-IMM, STATUS_WE=1 (ALU_OP=13 AND at T3, JMP_BZ_BN_CALL selects R[rd])
        test = STAT | IMM | EXT(1) | BUS(IMMB)  # T3: Test R[rd] & 0xFFFF and latch Z, N flags into Status Register
        taken = z if op == 20 else n
        if not taken:
            return [test]                       # T4 (not taken): falls through to IDLE (STEP_RST=1) | T <- 0
        return [
            test,                               # T3: STATUS_WE=1, BUS<-0xFFFF (ALU_OP=AND)          | Z, N <- flags(R[rd] & 0xFFFF)
            ACC | BUS(PC),                      # T4: BUS<-PC, ACC_LOAD=1 (ALU_B=REL_8, ALU_OP=ADD)  | ACC <- PC + (sext(off8) << 1)
            STEP_RST | PC_LOAD | BUS(ACCB),     # T5: BUS<-ACC, PC_LOAD=1 (PC_FETCH_EN=1), STEP_RST=1| PC <- ACC, T <- 0
        ]

    if op == 22:                                # JMP off11 (0x16)
        return [
            ACC | BUS(PC),                      # T3: BUS<-PC, ACC_LOAD=1 (ALU_B=REL_11, ALU_OP=ADD) | ACC <- PC + (sext(off11) << 1)
            STEP_RST | PC_LOAD | BUS(ACCB),     # T4: BUS<-ACC, PC_LOAD=1 (PC_FETCH_EN=1), STEP_RST=1| PC <- ACC, T <- 0
        ]

    if op == 23:                                # CALL off11 (0x17)
        return [
            ACC | BUS(PC),                         # T3: BUS<-PC, ACC_LOAD=1 (ALU_B=REL_11, ALU_OP=ADD) | ACC <- PC + (sext(off11) << 1)
            REG_WE | BUS(PC),                   # T4: BUS<-PC, REG_WE=1 (REG_D=6 in Format F6)       | R6 <- PC (save return address)
            STEP_RST | PC_LOAD | BUS(ACCB),     # T5: BUS<-ACC, PC_LOAD=1 (PC_FETCH_EN=1), STEP_RST=1| PC <- ACC, T <- 0
        ]

    if op == 24:                                # RET / JR rd (0x18)
        return [
            STEP_RST | PC_LOAD | BUS(REG),      # T3: BUS<-R[rd] (REG_A=RD), PC_LOAD=1, STEP_RST=1   | PC <- R[rd], T <- 0
        ]

    if op == 25:                                # PUSH rd (0x19)
        return [
            MDR | BUS(REG),                     # T3: BUS<-R[rd] (REG_A=RD), MDR_LOAD=1              | MDR <- R[rd]
            ACC | IMM | EXT(1) | BUS(IMMB),     # T4: BUS<-0xFFFF (-1), ACC_LOAD=1 (REG_B=7, ADD)    | ACC <- R7 - 1
            REG_WE | BUS(ACCB),                 # T5: BUS<-ACC, REG_WE=1 (REG_D=7 since BSRC==5)     | R7 <- ACC (R7 - 1)
            ACC | IMM | EXT(1) | BUS(IMMB),     # T6: BUS<-0xFFFF (-1), ACC_LOAD=1 (REG_B=7, ADD)    | ACC <- R7 - 2
            MAR | REG_WE | BUS(ACCB),           # T7: BUS<-ACC, MAR_LOAD=1, REG_WE=1 (REG_D=7)       | MAR <- ACC, R7 <- ACC (R7 - 2)
            STEP_RST | MEM_W | BUS(MDRB),       # T8: BUS<-MDR, MEM_WRITE=1, STEP_RST=1              | RAM[MAR>>1] <- MDR, T <- 0
        ]

    if op == 26: 
        return [
             MAR | BUS(REG),                               # T3: MAR <- R7 (REG_A forced to R7)
             MDR | MEM_R | BUS(RAM),                       # T4: MDR <- Mem[MAR]
             ACC | IMM | EXT(1) | BUS(IMMB),               # T5: ACC <- R7 + 1  (SUB with 0xFFFF)
             REG_WE | BUS(ACCB),                           # T6: R7 <- ACC
             ACC | IMM | EXT(1) | BUS(IMMB),               # T7: ACC <- R7 + 1
             REG_WE | BUS(ACCB),                           # T8: R7 <- ACC
             STEP_RST | REG_WE | BUS(MDRB)                 # T9: Rd <- MDR
        ]
        
    return []                                   # Unimplemented opcodes (12, 27-31): T3 falls through to IDLE (STEP_RST=1)

def build():
    rom = [IDLE] * 2048
    for z in (0, 1):
        for n in (0, 1):
            for op in range(32):
                base = (z << 10) | (n << 9) | (op << 4)
                for t, w in enumerate(FETCH):
                    rom[base + t] = w
                for t, w in enumerate(op_rows(op, z, n), start=3):
                    assert t < 16, f"op {op} too long"
                    rom[base + t] = w
    return rom


def verify_rom(rom):
    """Raise AssertionError if any documented control-ROM invariant fails."""
    assert len(rom) == 2048, f"ROM must contain 2048 words, got {len(rom)}"
    for addr, word in enumerate(rom):
        assert isinstance(word, int) and 0 <= word <= 0xFFFF, (
            f"control word out of 16-bit range at address 0x{addr:03x}: {word!r}")
        bus_source = (word >> 11) & 0b111
        assert 0 <= bus_source <= 7, f"invalid BUS_SOURCE at address 0x{addr:03x}"
        assert not (word & MEM_R and word & MEM_W), (
            f"MEM_READ and MEM_WRITE both asserted at address 0x{addr:03x}")
        if word & MEM_R:
            assert word & MDR and bus_source == RAM, (
                f"unsafe memory read at address 0x{addr:03x}")
        if word & MEM_W:
            assert bus_source == MDRB, (
                f"memory write without MDR driving bus at address 0x{addr:03x}")
        if word & (REG_WE | MEM_W):
            assert bus_source != OFF, (
                f"write enable asserted with no bus driver at address 0x{addr:03x}")

    # Uniform fetch sequence for every opcode and flag quadrant.
    for z in (0, 1):
        for n in (0, 1):
            for op in range(32):
                base = (z << 10) | (n << 9) | (op << 4)
                assert rom[base:base + 3] == FETCH, (
                    f"fetch sequence differs for Z={z}, N={n}, opcode={op}")

    # Non-branch opcodes must be quadrant-independent for all 16 T-states.
    for op in range(32):
        if op in (20, 21):
            continue
        reference = rom[(op << 4):(op << 4) + 16]
        for z, n in ((0, 1), (1, 0), (1, 1)):
            base = (z << 10) | (n << 9) | (op << 4)
            assert rom[base:base + 16] == reference, (
                f"non-branch quadrant mismatch for opcode={op}, Z={z}, N={n}")

    # Every instruction path must reach STEP_RST or HALT by T15.
    # For conditional branches, check both flag values through their actual ROM rows.
    for z in (0, 1):
        for n in (0, 1):
            for op in range(32):
                base = (z << 10) | (n << 9) | (op << 4)
                terminated = False
                for t in range(3, 16):
                    word = rom[base + t]
                    if word & (STEP_RST | HALT):
                        terminated = True
                        break
                assert terminated, (
                    f"instruction path does not terminate: opcode={op}, Z={z}, N={n}")

    # PC_LOAD is allowed only for sequential fetch increment or control transfers.
    for z in (0, 1):
        for n in (0, 1):
            for op in range(32):
                base = (z << 10) | (n << 9) | (op << 4)
                for t in range(16):
                    if not (rom[base + t] & PC_LOAD):
                        continue
                    legal = (t == 1 or
                             (op in (20, 21) and (z if op == 20 else n) and t == 5) or
                             (op == 22 and t == 4) or
                             (op == 23 and t == 5) or
                             (op == 24 and t == 3))
                    assert legal, (
                        f"illegal PC_LOAD at opcode={op}, Z={z}, N={n}, T={t}")

    # Branch polarity and the T3 zero-test encoding are fixed by specification.
    for z in (0, 1):
        for n in (0, 1):
            for op, flag in ((20, z), (21, n)):
                base = (z << 10) | (n << 9) | (op << 4)
                test = rom[base + 3]
                assert test == (STAT | IMM | EXT(1) | BUS(IMMB)), (
                    f"branch opcode {op} does not test Rt AND 0xFFFF at T3")
                if flag:
                    assert rom[base + 5] & (STEP_RST | PC_LOAD) == (STEP_RST | PC_LOAD), (
                        f"taken branch target load is malformed for opcode={op}, Z={z}, N={n}")
                else:
                    assert rom[base + 4] == IDLE, (
                        f"branch fallthrough is not SAFE/IDLE for opcode={op}, Z={z}, N={n}")

    # Unimplemented opcodes are harmless four-cycle NOPs (fetch T0-T2 + SAFE at T3).
    for op in (12, 27, 28, 29, 30, 31):
        for z in (0, 1):
            for n in (0, 1):
                base = (z << 10) | (n << 9) | (op << 4)
                assert rom[base + 3] == IDLE, (
                    f"unimplemented opcode {op} lacks SAFE=0x3801 at T3")
                assert all(rom[base + t] == IDLE for t in range(4, 16)), (
                    f"unimplemented opcode {op} modifies state after T3")

    # Stack operations must retain their specified sequencing and terminate.
    # Row counts come from op_rows(), so the checks follow the microcode length
    # (PUSH: T3-T8, POP: T3-T9) instead of hard-coded T-state numbers.
    for z in (0, 1):
        for n in (0, 1):
            push = (z << 10) | (n << 9) | (25 << 4)
            pop = (z << 10) | (n << 9) | (26 << 4)
            push_rows, pop_rows = op_rows(25, z, n), op_rows(26, z, n)
            push_end, pop_end = 3 + len(push_rows) - 1, 3 + len(pop_rows) - 1
            assert [rom[push + 3 + i] for i in range(len(push_rows))] == push_rows, "PUSH sequence mismatch"
            assert [rom[pop + 3 + i] for i in range(len(pop_rows))] == pop_rows, "POP sequence mismatch"
            assert rom[push + push_end] & (STEP_RST | MEM_W) == (STEP_RST | MEM_W), "PUSH must finish with memory write"
            assert rom[pop + pop_end] & (STEP_RST | REG_WE) == (STEP_RST | REG_WE), "POP must finish with register write"
            # Nothing may follow the last row of either instruction.
            assert all(rom[push + t] == IDLE for t in range(push_end + 1, 16)), "PUSH has stray rows after its last step"
            assert all(rom[pop + t] == IDLE for t in range(pop_end + 1, 16)), "POP has stray rows after its last step"
            # POP: MAR <- R7 (T3), MDR <- Mem[MAR] (T4), SP <- SP + 1 twice via ACC (T5-T8), Rd <- MDR (T9).
            assert rom[pop + 3] == (MAR | BUS(REG)), "POP T3 must load MAR from the register port (R7)"
            assert rom[pop + 4] == (MDR | MEM_R | BUS(RAM)), "POP T4 must read memory into MDR"
            for acc_t in (5, 7):
                assert rom[pop + acc_t] == (ACC | IMM | EXT(1) | BUS(IMMB)), f"POP T{acc_t} must compute SP +/- 0xFFFF into ACC"
                assert rom[pop + acc_t + 1] == (REG_WE | BUS(ACCB)), f"POP T{acc_t + 1} must write ACC back to SP"
            assert rom[pop + 9] == (STEP_RST | REG_WE | BUS(MDRB)), "POP T9 must write MDR to Rd and end the instruction"
            # POP performs exactly one memory access after fetch (the read at T4), before SP changes.
            assert [t for t in range(3, 16) if rom[pop + t] & (MEM_R | MEM_W)] == [4], "POP must access memory exactly once, at T4"

    # MOV (op 2): single-step register copy through port A, finishing at T3 (4 cycles total).
    for z in (0, 1):
        for n in (0, 1):
            mov = (z << 10) | (n << 9) | (2 << 4)
            assert rom[mov + 3] == (STEP_RST | REG_WE | BUS(REG)), "MOV T3 must copy R[port A] into Rd and end the instruction"
            assert all(rom[mov + t] == IDLE for t in range(4, 16)), "MOV has stray rows after T3"
            assert not (rom[mov + 3] & (ACC | MAR | MDR | MEM_R | MEM_W | PC_LOAD | STAT)), "MOV must not touch ACC, memory, PC or flags"

    # The non-ROM hardware signals are specified by these exact equations.
    # Exhaustively evaluate the equations at all 2048 ROM addresses so this
    # generator's hardware-signal contract cannot silently drift.
    for addr in range(2048):
        op, t = (addr >> 4) & 0x1F, addr & 0xF
        ir_load = (t == 2)
        pc_fetch_en = (t != 1)
        byte_op = (op in (7, 8)) and (t == 6)
        def alu_opcode_hw(op, t):
            if op == 4: return 13 if t == 3 else 14
            if op in (20, 21) and t == 3: return 13
            if op == 26: return 13 if t == 3 else 10
            return op
        assert ir_load == (t == 2) and pc_fetch_en == (t != 1), "fetch hardware-signal contract mismatch"
        assert byte_op == ((op in (7, 8)) and (t == 6)), "BYTE_OP contract mismatch"
        assert alu_opcode_hw(op, t) == (13 if (op in (4, 26, 20, 21) and t == 3) else (14 if op == 4 else (10 if op == 26 else op))), "ALU_OPCODE contract mismatch"


# ---- required consistency checks (reported in the log) ---------------------
FIELD_BITS = {                     # name -> (lsb, width), as in the layout at the top of this file
    "STEP_RST": (0, 1), "MAR_LOAD": (1, 1), "MDR_LOAD": (2, 1), "ACC_LOAD": (3, 1),
    "REG_WE": (4, 1), "MEM_READ": (5, 1), "MEM_WRITE": (6, 1), "STATUS_WE": (7, 1),
    "IMM": (8, 1), "IMM_BIT_EXTEND": (9, 2), "BUS_SOURCE": (11, 3),
    "PC_LOAD": (14, 1), "HALT": (15, 1),
}
BUS_NAMES = {PC: "PC", MDRB: "MDR", IRB: "IR/REL", IMMB: "IMM",
             REG: "REG", ACCB: "ACC", RAM: "RAM", OFF: "OFF"}
IMPLEMENTED_OPCODES = set(range(27)) - {12}        # 12 (MUL) and 27-31 are undefined
WRITE_ENABLES = MAR | MDR | ACC | REG_WE | MEM_W | STAT   # PC_LOAD / IR_LOAD handled separately
QUADRANTS = [(z, n) for z in (0, 1) for n in (0, 1)]


def run_checks(rom):
    """Run the required consistency checks; return (all_passed, log_lines)."""
    log, ok = [], True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= passed
        log.append(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    def base(z, n, op): return (z << 10) | (n << 9) | (op << 4)

    # (1) no control word selects more than one bus source
    #     BUS_SOURCE is one 3-bit encoded field: a word names exactly one source as long as
    #     no other field shares its bits and the field encoders agree with the layout.
    bad = []
    spans = sorted((lsb, lsb + w, nm) for nm, (lsb, w) in FIELD_BITS.items())
    for (l0, h0, n0), (l1, h1, n1) in zip(spans, spans[1:]):
        if l1 < h0:
            bad.append(f"fields {n0}/{n1} overlap")
    for nm, mask in (("STEP_RST", STEP_RST), ("MAR_LOAD", MAR), ("MDR_LOAD", MDR), ("ACC_LOAD", ACC),
                     ("REG_WE", REG_WE), ("MEM_READ", MEM_R), ("MEM_WRITE", MEM_W),
                     ("STATUS_WE", STAT), ("IMM", IMM), ("PC_LOAD", PC_LOAD), ("HALT", HALT)):
        if mask != 1 << FIELD_BITS[nm][0]:
            bad.append(f"{nm} encoder disagrees with layout")
    for a, w in enumerate(rom):
        if sum(1 for code in BUS_NAMES if (w >> 11) & 0b111 == code) != 1:
            bad.append(f"0x{a:03X}")
    report("no control word selects more than one bus source", not bad,
           f"{len(bad)} problems, e.g. {bad[:3]}" if bad else "")

    # (2) every implemented instruction eventually asserts STEP_RST or HALT
    missing = sorted({op for op in IMPLEMENTED_OPCODES for z, n in QUADRANTS
                      if not any(rom[base(z, n, op) + t] & (STEP_RST | HALT) for t in range(3, 16))})
    report("every implemented instruction reaches STEP_RST or HALT", not missing,
           "opcodes " + ", ".join(map(str, missing)) if missing else "")

    # (3) MEM_READ and MEM_WRITE never together
    both = [a for a, w in enumerate(rom) if w & MEM_R and w & MEM_W]
    report("MEM_READ and MEM_WRITE never asserted together", not both,
           f"{len(both)} words" if both else "")

    # (4) write enables never asserted without valid source data
    #     Every write enable needs a driven bus (BUS_SOURCE != OFF), including the hardware-
    #     derived IR_LOAD (T2) and a PC load from the bus (PC_LOAD outside T1, where
    #     PC_FETCH_EN=0 selects PC+2 instead); a RAM bus read also needs MEM_READ.
    wr = []
    for a, w in enumerate(rom):
        t, bus = a & 0xF, (w >> 11) & 0b111
        writes = (w & WRITE_ENABLES) or t == 2 or ((w & PC_LOAD) and t != 1)
        if writes and (bus == OFF or (bus == RAM and not w & MEM_R)):
            wr.append(a)
    report("write enables never asserted without valid source data", not wr,
           f"{len(wr)} words" if wr else "")

    # (5) conditional-branch words differ only in respect of the relevant condition signal
    #     BZ (20) may depend on Z only, BN (21) on N only; their fetch and T3 test words are
    #     common to all quadrants; every other opcode ignores both flags.
    diff = []
    for op in range(32):
        for t in range(16):
            for z, n in QUADRANTS:
                if op == 20:
                    other = rom[base(z, 1 - n, op) + t]
                elif op == 21:
                    other = rom[base(1 - z, n, op) + t]
                else:
                    other = rom[base(0, 0, op) + t]
                if rom[base(z, n, op) + t] != other:
                    diff.append((op, t))
        if op in (20, 21):
            for t in range(4):
                if len({rom[base(z, n, op) + t] for z, n in QUADRANTS}) != 1:
                    diff.append((op, t))
    report("conditional-branch words differ only in the relevant condition signal", not diff,
           f"{len(diff)} rows, e.g. {sorted(set(diff))[:3]}" if diff else
           "BZ depends on Z only, BN on N only, all other opcodes ignore Z and N")

    # (6) no undefined opcode is capable of modifying architectural state
    leak = [(op, t) for op in range(32) if op not in IMPLEMENTED_OPCODES
            for z, n in QUADRANTS for t in range(3, 16)
            if rom[base(z, n, op) + t] & (WRITE_ENABLES | PC_LOAD)]
    report("no undefined opcode can modify architectural state", not leak,
           f"{len(leak)} words" if leak else "")

    return ok, log


# ---- output helpers -------------------------------------------------------
def rle(words):
    out, i = [], 0
    while i < len(words):
        j = i
        while j < len(words) and words[j] == words[i]: j += 1
        out.append(f"{j-i}*{words[i]:x}" if j - i > 1 else f"{words[i]:x}")
        i = j
    lines, cur = [], ""
    for tok in out:
        if len(cur) + len(tok) + 1 > 60: lines.append(cur); cur = tok
        else: cur = (cur + " " + tok).strip()
    lines.append(cur)
    return "\n".join(lines)

def write_hex(rom, path="control_rom.hex"):
    with open(path, "w") as f:
        f.write("v2.0 raw\n" + rle(rom) + "\n")

def patch_circ(src, dst, rom):
    t = open(src, newline="").read()
    nl = "\r\n" if "\r\n" in t else "\n"
    pat = re.compile(r'(<a name="contents">addr/data: 11 16)\r?\n.*?(</a>)', re.S)
    assert len(pat.findall(t)) == 1, "ROM block not found / not 16-bit"
    body = rle(rom).replace("\n", nl)
    t = pat.sub(lambda m: m.group(1) + nl + body + nl + m.group(2), t)
    open(dst, "w", newline="").write(t)

if __name__ == "__main__":
    rom = build()
    ok, log = run_checks(rom)
    print("Consistency checks:")
    print("\n".join(log))
    if not ok:
        raise SystemExit("\nCHECKS FAILED -- no ROM file written.")
    verify_rom(rom)
    write_hex(rom)
    outputs = ["control_rom.hex"]
    if len(sys.argv) == 3:
        patch_circ(sys.argv[1], sys.argv[2], rom)
        outputs.append(sys.argv[2])
    elif len(sys.argv) != 1:
        raise SystemExit("usage: python3 G06_microcode_gen.py [input.circ output.circ]")
    print(f"Verification passed: {len(rom)} ROM words; all microcode invariants hold. Wrote {', '.join(outputs)}.")
