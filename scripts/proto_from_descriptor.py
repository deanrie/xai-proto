"""Render .proto source from the descriptors compiled into xai-sdk-python.

Usage (run with the xai-sdk-python environment active):

    uv run python proto_from_descriptor.py <out_dir> xai/api/v1/collections.proto ...

File-level options (java_package and friends) are left out: in xai-proto they
come from buf's managed mode at generation time, not from the source files.
Comments cannot be recovered; the gencode carries no source info.
"""

import importlib
import os
import sys

from google.protobuf import descriptor_pb2
from google.protobuf.descriptor_pb2 import FieldDescriptorProto as F

TYPE_NAMES = {
    F.TYPE_DOUBLE: "double", F.TYPE_FLOAT: "float", F.TYPE_INT64: "int64",
    F.TYPE_UINT64: "uint64", F.TYPE_INT32: "int32", F.TYPE_FIXED64: "fixed64",
    F.TYPE_FIXED32: "fixed32", F.TYPE_BOOL: "bool", F.TYPE_STRING: "string",
    F.TYPE_BYTES: "bytes", F.TYPE_UINT32: "uint32", F.TYPE_SFIXED32: "sfixed32",
    F.TYPE_SFIXED64: "sfixed64", F.TYPE_SINT32: "sint32", F.TYPE_SINT64: "sint64",
}

MODULES = {
    "xai/api/v1/collections.proto": "xai_sdk.proto.v6.collections_pb2",
    "xai/api/v1/shared.proto": "xai_sdk.proto.v6.shared_pb2",
    "xai/api/v1/types.proto": "xai_sdk.proto.v6.types_pb2",
}


def type_ref(field, scope_pkg):
    if field.type in (F.TYPE_MESSAGE, F.TYPE_ENUM):
        name = field.type_name  # fully qualified, leading dot
        prefix = "." + scope_pkg + "."
        if scope_pkg and name.startswith(prefix):
            return name[len(prefix):]
        return name.lstrip(".")
    return TYPE_NAMES[field.type]


def field_options(field):
    opts = []
    if field.options.deprecated:
        opts.append("deprecated = true")
    if field.json_name and field.json_name != default_json_name(field.name):
        opts.append(f'json_name = "{field.json_name}"')
    return f" [{', '.join(opts)}]" if opts else ""


def default_json_name(name):
    out, upper = [], False
    for ch in name:
        if ch == "_":
            upper = True
        elif upper:
            out.append(ch.upper())
            upper = False
        else:
            out.append(ch)
    return "".join(out)


def render_enum(enum, indent):
    pad = "  " * indent
    lines = [f"{pad}enum {enum.name} {{"]
    if enum.options.allow_alias:
        lines.append(f"{pad}  option allow_alias = true;")
    if enum.options.deprecated:
        lines.append(f"{pad}  option deprecated = true;")
    for v in enum.value:
        opt = " [deprecated = true]" if v.options.deprecated else ""
        lines.append(f"{pad}  {v.name} = {v.number}{opt};")
    for r in enum.reserved_range:
        lines.append(f"{pad}  reserved {r.start}{'' if r.end == r.start else f' to {r.end}'};")
    for n in enum.reserved_name:
        lines.append(f'{pad}  reserved "{n}";')
    lines.append(f"{pad}}}")
    return lines


def render_message(msg, pkg, indent):
    pad = "  " * indent
    lines = [f"{pad}message {msg.name} {{"]
    if msg.options.deprecated:
        lines.append(f"{pad}  option deprecated = true;")
    map_entries = {m.name: m for m in msg.nested_type if m.options.map_entry}
    for nested in msg.nested_type:
        if nested.options.map_entry:
            continue
        lines += render_message(nested, pkg, indent + 1)
    for enum in msg.enum_type:
        lines += render_enum(enum, indent + 1)

    oneof_fields = {}
    plain = []
    for f in msg.field:
        if f.HasField("oneof_index") and not f.proto3_optional:
            oneof_fields.setdefault(f.oneof_index, []).append(f)
        else:
            plain.append(f)

    emitted_oneofs = set()
    for f in msg.field:
        if f.HasField("oneof_index") and not f.proto3_optional:
            idx = f.oneof_index
            if idx in emitted_oneofs:
                continue
            emitted_oneofs.add(idx)
            lines.append(f"{pad}  oneof {msg.oneof_decl[idx].name} {{")
            for of in oneof_fields[idx]:
                lines.append(f"{pad}    {type_ref(of, pkg)} {of.name} = {of.number}{field_options(of)};")
            lines.append(f"{pad}  }}")
            continue
        entry_name = f.type_name.rsplit(".", 1)[-1] if f.type == F.TYPE_MESSAGE else None
        if entry_name in map_entries:
            entry = map_entries[entry_name]
            k, v = entry.field[0], entry.field[1]
            lines.append(f"{pad}  map<{type_ref(k, pkg)}, {type_ref(v, pkg)}> {f.name} = {f.number}{field_options(f)};")
            continue
        label = ""
        if f.label == F.LABEL_REPEATED:
            label = "repeated "
        elif f.proto3_optional:
            label = "optional "
        lines.append(f"{pad}  {label}{type_ref(f, pkg)} {f.name} = {f.number}{field_options(f)};")
    for r in msg.reserved_range:
        end = "" if r.end == r.start + 1 else f" to {r.end - 1}"
        lines.append(f"{pad}  reserved {r.start}{end};")
    for n in msg.reserved_name:
        lines.append(f'{pad}  reserved "{n}";')
    lines.append(f"{pad}}}")
    return lines


def render_service(svc, pkg):
    lines = [f"service {svc.name} {{"]
    if svc.options.deprecated:
        lines.append("  option deprecated = true;")
    for m in svc.method:
        inp = ("stream " if m.client_streaming else "") + strip_pkg(m.input_type, pkg)
        out = ("stream " if m.server_streaming else "") + strip_pkg(m.output_type, pkg)
        if m.options.deprecated:
            lines.append(f"  rpc {m.name}({inp}) returns ({out}) {{")
            lines.append("    option deprecated = true;")
            lines.append("  }")
        else:
            lines.append(f"  rpc {m.name}({inp}) returns ({out}) {{}}")
    lines.append("}")
    return lines


def strip_pkg(name, pkg):
    prefix = "." + pkg + "."
    return name[len(prefix):] if pkg and name.startswith(prefix) else name.lstrip(".")


def render_file(fd):
    lines = [f'syntax = "{fd.syntax or "proto3"}";', ""]
    if fd.package:
        lines += [f"package {fd.package};", ""]
    for dep in fd.dependency:
        lines.append(f'import "{dep}";')
    if fd.dependency:
        lines.append("")
    for enum in fd.enum_type:
        lines += render_enum(enum, 0) + [""]
    for msg in fd.message_type:
        lines += render_message(msg, fd.package, 0) + [""]
    for svc in fd.service:
        lines += render_service(svc, fd.package) + [""]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:] or list(MODULES)
    for name in names:
        mod = importlib.import_module(MODULES[name])
        fd = descriptor_pb2.FileDescriptorProto()
        mod.DESCRIPTOR.CopyToProto(fd)
        path = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(render_file(fd))
        print(path)


if __name__ == "__main__":
    main()
