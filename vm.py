import argparse
import collections
import enum
import io


class State(enum.Enum):
    READY = enum.auto()
    HALTED = enum.auto()
    INPUT_BLOCKED = enum.auto()


class Vm:
    def __init__(self, memory: list[int], stack: list[int], ip: int) -> None:
        self.memory = memory
        self.stack = stack
        self.ip = ip
        self.state = State.READY
        self.reader = io.StringIO()
        self.writer = io.StringIO()

    @classmethod
    def from_file(cls, file: str) -> "Vm":
        instructions = []
        with open(file, "rb") as f:
            while word := f.read(2):
                num = int.from_bytes(word, byteorder="little", signed=False)
                instructions.append(num)
        memory = instructions + [0] * (2**15 - len(instructions) + 8)
        return cls(memory, [], 0)

    @classmethod
    def from_dump(cls, dump: tuple[tuple[int, ...], tuple[int, ...], int]) -> "Vm":
        memory, stack, ip = dump
        return cls(list(memory), list(stack), ip)

    def dump(self) -> tuple[tuple[int, ...], tuple[int, ...], int]:
        return (tuple(self.memory), tuple(self.stack), self.ip)

    def input(self, s: str) -> None:
        pos = self.reader.tell()
        self.reader.write(s)
        self.reader.seek(pos)
        self.state = State.READY

    def output(self) -> str:
        s = self.writer.getvalue()
        self.writer.truncate(0)
        self.writer.seek(0)
        return s

    def grab(self) -> int:
        result = self.memory[self.ip]
        self.ip += 1
        if result <= 32775:
            return result
        raise ValueError(f"Invalid number {result}")

    def val(self, i: int) -> int:
        if i <= 32767:
            return i
        if i <= 32775:
            return self.memory[i]
        raise ValueError(f"Invalid number {i}")

    def run(self) -> None:
        while self.state == State.READY:
            self.step()

    def step(self) -> None:
        g = self.grab
        v = self.val
        op = g()
        match op:
            case 0:  # halt: 0; stop execution and terminate the program
                self.state = State.HALTED
            case 1:  # set: 1 a b; set register <a> to the self.value of <b>
                a, b = g(), g()
                self.memory[a] = v(b)
            case 2:  # push: 2 a; push <a> onto the self.stack
                a = g()
                self.stack.append(v(a))
            case 3:  # pop: 3 a; remove the top element from the self.stack and write it into <a>; empty self.stack = error
                a = g()
                self.memory[a] = self.stack.pop()
            case 4:  # eq: 4 a b c; set <a> to 1 if <b> is equal to <c>; set it to 0 otherwise
                a, b, c = g(), g(), g()
                self.memory[a] = int(v(b) == v(c))
            case 5:  # gt: 5 a b c; set <a> to 1 if <b> is greater than <c>; set it to 0 otherwise
                a, b, c = g(), g(), g()
                self.memory[a] = int(v(b) > v(c))
            case 6:  # jmp: 6 a; jump to <a>
                a = g()
                self.ip = v(a)
            case 7:  # jt: 7 a b; if <a> is nonzero, jump to <b>
                a, b = g(), g()
                if v(a):
                    self.ip = v(b)
            case 8:  # jf: 8 a b; if <a> is zero, jump to <b>
                a, b = g(), g()
                if not v(a):
                    self.ip = v(b)
            case 9:  # add: 9 a b c; assign into <a> the sum of <b> and <c> (modulo 32768)
                a, b, c = g(), g(), g()
                self.memory[a] = (v(b) + v(c)) % 32768
            case 10:  # mult: 10 a b c; store into <a> the product of <b> and <c> (modulo 32768)
                a, b, c = g(), g(), g()
                self.memory[a] = (v(b) * v(c)) % 32768
            case 11:  # mod: 11 a b c; store into <a> the remainder of <b> divided by <c>
                a, b, c = g(), g(), g()
                self.memory[a] = v(b) % v(c)
            case 12:  # and: 12 a b c; stores into <a> the bitwise and of <b> and <c>
                a, b, c = g(), g(), g()
                self.memory[a] = v(b) & v(c)
            case 13:  # or: 13 a b c; stores into <a> the bitwise or of <b> and <c>
                a, b, c = g(), g(), g()
                self.memory[a] = v(b) | v(c)
            case 14:  # not: 14 a b; stores 15-bit bitwise inverse of <b> in <a>
                a, b = g(), g()
                self.memory[a] = ((1 << 15) - 1) & ~v(b)
            case 15:  # rmem: 15 a b; read memory at address <b> and write it to <a>
                a, b = g(), g()
                # memory[a] = get(b)
                self.memory[a] = self.memory[v(b)]
                # memory[a] = memory[b]
            case 16:  # wmem: 16 a b; write the value from <b> into memory at address <a>
                a, b = g(), g()
                self.memory[v(a)] = v(b)
            case 17:  # call: 17 a; write the address of the next instruction to the self.stack and jump to <a>
                a = g()
                self.stack.append(self.ip)
                self.ip = v(a)
            case 18:  # ret: 18; remove the top element from the self.stack and jump to it; empty self.stack = halt
                if not self.stack:
                    self.state = State.HALTED
                else:
                    self.ip = self.stack.pop()
            case 19:  # out: 19 a; write the character represented by ascii code <a> to the terminal
                a = g()
                self.writer.write(chr(v(a)))
            case 20:  # in: 20 a; read a character from the terminal and write its ascii code to <a>; it can be assumed that once input starts, it will continue until a newline is encountered; this means that you can safely read whole lines from the keyboard instead of having to figure out how to read individual characters
                a = g()
                ch = self.reader.read(1)
                if not ch:
                    self.state = State.INPUT_BLOCKED
                    self.ip -= 2
                else:
                    self.memory[a] = ord(ch)
            case 21:  # noop: 21; no operation
                pass


def parse_room(s: str) -> tuple:
    paragraphs = s.split("\n\n")
    assert paragraphs[0] == "", f"First line not blank: '{paragraphs[0]}' ->\n{s}"
    title, text = paragraphs[1].splitlines()
    assert title.startswith("=="), f"Incorrect title format '{title}' ->\n{s}"
    title = title.removeprefix("== ").removesuffix(" ==")

    interests = []
    exits = []

    if len(paragraphs) == 5:
        interests = [line[2:] for line in paragraphs[2].splitlines()[1:]]
        exits = [line[2:] for line in paragraphs[3].splitlines()[1:]]
    elif len(paragraphs) == 4:
        exits = [line[2:] for line in paragraphs[2].splitlines()[1:]]
    else:
        assert False, f"Unexpected number of paragraphs '{len(paragraphs)}' ->\n{s}"

    assert paragraphs[-1] == "What do you do?\n", f"Incorrect footer '{paragraphs[-1]}' ->\n{s}"
    return title, text, interests, exits


def resume(vm: Vm) -> None:
    print('--- Resuming VM ---')
    vm.input("look\n")
    while True:
        assert vm.state == State.READY
        vm.run()

        print(vm.output())

        # dump = vm.dump()
        # if dump in seen:
        #     print('--- State seen previously ---')
        # seen.add(dump)

        if vm.state == State.INPUT_BLOCKED:
            # Parse Room
            vm.input("look\n")
            vm.run()
            # title, text, interests, exits = parse_room(vm.output())
            # print(f'{title=} {interests=} {exits=}')

            inp = input()
            if inp == "q":  # Custom quit command
                break
            if inp.startswith("d "):  # Custom dump command
                with open(inp.split(" ", 1)[1], "w") as f:
                    f.write(str(vm.dump()))
            vm.input(inp + "\n")
        else:
            break
    print("--- VM Exited ---")

def main() -> None:
    parser = argparse.ArgumentParser("vm")
    parser.add_argument(
        "file", help="Path of bin file.", default="./challenge.bin", type=str, nargs="?"
    )
    args = parser.parse_args()

    vm = Vm.from_file(args.file)

    vm.input("\n".join([
        'take tablet',
        'doorway',
        'north',
        'north',
        'bridge',
        'continue',
        'down',
        'east',
        'take empty lantern',
        'west',
        'west',
        'passage',
        'ladder' # Twisty passages
    ]) + "\n")
    vm.run()
    vm.output()


    # vm.input("look\n")
    # resume(vm)

    seen = {vm.dump()}
    q = collections.deque([vm.dump()])
    while q:
        dump = q.popleft()
        vm = Vm.from_dump(dump)

        vm.input("look\n")
        vm.run()
        title, text, interests, exits = parse_room(vm.output())

        if title != "Twisty passages":
            print(f"New title: {title}")
            resume(vm)
        elif interests:
            print(f"New interests: {interests}")
            resume(vm)
        elif any(exit not in ["ladder", "north", "east", "south", "west"] for exit in exits):
            print(f"New exits: {exits}")
            resume(vm)

        for exit in exits:
            if exit == "ladder":
                continue

            vm = Vm.from_dump(dump)
            vm.input(f"{exit}\n")
            vm.run()

            dump2 = vm.dump()
            if dump2 in seen:
                continue
            seen.add(dump2)
            q.append(dump2)


if __name__ == "__main__":
    main()


# Results:
# $ echo -n "<Code Here>" | md5sum

# 76ec2408e8fe3f1753c25db51efd8eb3
# 0e6aa7be1f68d930926d72b3741a145c DONE (first output)
# 7997a3b2941eab92c1c0345d5747b420 DONE (successful self-test)
# 186f842951c0dcfe8838af1e7222b7d4 DONE (tablet)
# 2bf84e54b95ce97aefd9fc920451fc45
# e09640936b3ef532b7b8e83ce8f125f4 DONE (teleporter)
# 4873cf6b76f62ac7d5a53605b2535a0c
# d0c54d4ed7f943280ce3e19532dbb1a6
