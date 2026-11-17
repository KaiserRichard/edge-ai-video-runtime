import argparse
import asyncio
import math

from .hub import Hub, Server, TelemetryProtocol
from .replay import load_replay, play
from .synthetic import generate


def arguments(argv=None):
    parser = argparse.ArgumentParser(description="Read-only CN / OS live demo dashboard")
    parser.add_argument("--mode", choices=("live", "synthetic", "replay"), default="synthetic")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--udp-host", default="0.0.0.0")
    parser.add_argument("--pi-port", type=int, default=5006)
    parser.add_argument("--receiver-port", type=int, default=5007)
    parser.add_argument("--replay", help="One CSV file or one run directory")
    parser.add_argument("--speed", type=float, default=1)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)
    if args.mode == "replay" and not args.replay:
        parser.error("--mode replay requires --replay PATH")
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be finite and positive")
    if any(not 1 <= p <= 65535 for p in (args.port, args.pi_port, args.receiver_port)):
        parser.error("ports must be in 1..65535")
    if args.pi_port == args.receiver_port:
        parser.error("UDP ports must differ")
    return args


async def run(args):
    events = load_replay(args.replay) if args.mode == "replay" else None
    hub = Hub(args.mode, queue_size=512)
    server = Server(hub)
    transports = []
    producer = None
    listener = None
    try:
        listener = await asyncio.start_server(server.handle, args.host, args.port, limit=16384)
        if args.mode == "live":
            for port in (args.pi_port, args.receiver_port):
                transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: TelemetryProtocol(hub), local_addr=(args.udp_host, port))
                transports.append(transport)
        else:
            producer = asyncio.create_task(play(hub, events, args.speed, args.loop) if events is not None else generate(hub, args.seed))
            # Surface producer errors instead of leaving an apparently healthy UI.
            def completed(task):
                if not task.cancelled() and task.exception():
                    hub.status = f"source error: {task.exception()}"
            producer.add_done_callback(completed)
        print(f"Dashboard: http://{args.host}:{args.port}  mode={args.mode}", flush=True)
        if args.mode == "live":
            print(f"UDP Pi={args.pi_port}, receiver={args.receiver_port}; Ctrl+C to stop", flush=True)
        async with listener:
            await listener.serve_forever()
    finally:
        if producer:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        for transport in transports:
            transport.close()
        if listener:
            listener.close()
            await listener.wait_closed()
        await server.close()


def main():
    try:
        asyncio.run(run(arguments()))
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
