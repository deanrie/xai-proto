"""Compare the descriptors of the rebuilt .proto files (buf image) with the
descriptors compiled into xai-sdk-python. File options and source info are
ignored: the options come from buf managed mode, the gencode has no comments."""
import sys
from google.protobuf import descriptor_pb2, text_format
from xai_sdk.proto.v6 import collections_pb2, shared_pb2, types_pb2

fds = descriptor_pb2.FileDescriptorSet()
fds.MergeFromString(open(sys.argv[1], "rb").read())
built = {f.name: f for f in fds.file}

def norm(fd):
    fd = descriptor_pb2.FileDescriptorProto.FromString(fd.SerializeToString())
    fd.DiscardUnknownFields()
    fd.ClearField("options"); fd.ClearField("source_code_info")
    return fd

ok = True
for mod in (collections_pb2, shared_pb2, types_pb2):
    orig = descriptor_pb2.FileDescriptorProto(); mod.DESCRIPTOR.CopyToProto(orig)
    a, b = norm(orig), norm(built[orig.name])
    same = a.SerializeToString(deterministic=True) == b.SerializeToString(deterministic=True)
    print(orig.name, "IDENTICAL" if same else "DIFFERENT")
    if not same:
        ok = False
        import difflib
        print("\n".join(difflib.unified_diff(text_format.MessageToString(a).splitlines(), text_format.MessageToString(b).splitlines(), "gencode", "rebuilt", lineterm="")))
sys.exit(0 if ok else 1)
