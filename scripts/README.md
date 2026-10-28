# Recovered proto sources

`collections.proto`, `shared.proto` and `types.proto` under `proto/xai/api/v1/`
on this branch are not xAI's source files. They are rendered from the
descriptors compiled into `xai-sdk-python` (`src/xai_sdk/proto/v6/*_pb2.py`)
by `proto_from_descriptor.py`, so the structure is exact and the comments are
missing. `compare_descriptors.py` checks that `buf build` of this tree yields
the same `FileDescriptorProto` for each file as the gencode, ignoring file
options (which buf managed mode adds at generation time) and source info.

Reproduce from a checkout of xai-sdk-python:

```sh
uv run python <this repo>/scripts/proto_from_descriptor.py <this repo>/proto
cd <this repo> && buf build -o /tmp/image.binpb
uv run python <this repo>/scripts/compare_descriptors.py /tmp/image.binpb
```

This branch exists as a reference for xai-org/xai-proto#83; it is not meant
to be merged.
