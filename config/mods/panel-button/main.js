// A tab-bar button that opens and closes one panel of the side panel stack, for panels whose own
// mod ships no button. Layout props: { panel: "<block id in panel-body>", label, icon }.
import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";
import { theme, run, props, layout, shared, setShared } from "herdr";

const find = (n, id) =>
  !n ? null : n.id === id ? n : (n.children ?? []).reduce((hit, c) => hit ?? find(c, id), null);

export default class PanelButton extends View {
  init(_props, _cx) {
    this.register();
  }

  // Herdr's tab bar restores each space's panel only from the "workspace.panels" list: add this
  // panel to it, and drop entries whose block is no longer in the stack (a removed panel). Runs once,
  // in init (a hot reload does not repeat it, and writing shared state while rendering has no effect).
  // Buttons that start at the same moment both read the list before either write lands, so the last
  // one erases the other: it only matters the first time, since later starts find their entry in place.
  register() {
    try {
      const id = props()?.panel;
      const inStack = (find(layout(), "panel-body")?.children ?? []).map((c) => c.id);
      // Props or layout not ready (or `herdr-app check`, which has no props): change nothing.
      if (!id || !inStack.includes(id)) return;
      const list = shared("workspace.panels") ?? ["files", "changes"];
      const next = list.filter((x) => inStack.includes(x));
      if (!next.includes(id)) next.push(id);
      if (next.length !== list.length || next.some((x, i) => x !== list[i]))
        setShared("workspace.panels", next);
    } catch {}
  }

  render(_cx) {
    const t = theme();
    const { panel: id, label, icon } = props() ?? {};
    const body = find(layout(), "panel-body");
    const shell = find(layout(), "panel");
    const on = Boolean(shell && !shell.hidden && body?.active === id);
    return h_flex()
      .size_full()
      .pr(10)
      .items_center()
      .justify_end()
      .bg(t.chrome)
      .border_b(1)
      .border_color(t.border)
      .child(
        h_flex()
          .id(`panel-${id}`)
          .h(26)
          .px(8)
          .gap(5)
          .flex_none()
          .items_center()
          .rounded(6)
          .text_size(12)
          .bg(on ? t.selected : t.chrome)
          .text_color(on ? t.foreground : t.muted)
          .hover((s) => s.bg(t.hover))
          .on_click(() => {
            if (on) run("layout.hide", { id: "panel" });
            else {
              run("layout.select", { stack: "panel-body", child: id });
              run("layout.show", { id: "panel" });
            }
          })
          .when(Boolean(icon), (el) => el.child(svg(icon).size(14)))
          .child(String(label ?? id ?? "Panel")),
      );
  }
}
