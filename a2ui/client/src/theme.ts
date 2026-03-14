/**
 * Dark theme for FreudAgent A2UI surfaces.
 * Minimal theme -- just enough to look decent with the Lit renderer.
 */

import { v0_8 } from "@a2ui/lit";

export const darkTheme: v0_8.Types.Theme = {
  additionalStyles: {
    Card: {
      background: "rgba(22, 27, 34, 0.8)",
      border: "1px solid rgba(48, 54, 61, 0.6)",
      borderRadius: "8px",
      padding: "16px",
    },
    Button: {
      borderRadius: "6px",
      padding: "8px 16px",
      cursor: "pointer",
    },
    Text: {
      h1: {},
      h2: {},
      h3: {},
      h4: {},
      h5: {},
      body: {},
      caption: { opacity: "0.7" },
    },
  },
  components: {
    AudioPlayer: {},
    Button: {
      "border-br-6": true,
      "layout-pt-2": true,
      "layout-pb-2": true,
      "layout-pl-4": true,
      "layout-pr-4": true,
      "color-bgc-p40": true,
    },
    Card: {
      "border-br-9": true,
      "layout-p-4": true,
      "color-bgc-n90": true,
    },
    CheckBox: {
      element: {},
      label: {},
      container: {},
    },
    Column: {
      "layout-g-2": true,
    },
    DateTimeInput: {
      container: {},
      label: {},
      element: {},
    },
    Divider: {},
    Image: {
      all: { "border-br-5": true },
      avatar: {},
      header: {},
      icon: {},
      largeFeature: {},
      mediumFeature: {},
      smallFeature: {},
    },
    Icon: {},
    List: {
      "layout-g-3": true,
    },
    Modal: {
      backdrop: {},
      element: {
        "border-br-9": true,
        "layout-p-4": true,
      },
    },
    MultipleChoice: {
      container: {},
      label: {},
      element: {},
    },
    Row: {
      "layout-g-3": true,
    },
    Slider: {
      container: {},
      label: {},
      element: {},
    },
    Tabs: {
      container: {},
      controls: { all: {}, selected: {} },
      element: {},
    },
    Text: {
      all: {},
      h1: {
        "typography-f-sf": true,
        "typography-w-500": true,
        "layout-m-0": true,
        "typography-sz-hs": true,
      },
      h2: {
        "typography-f-sf": true,
        "typography-w-500": true,
        "layout-m-0": true,
        "typography-sz-tl": true,
      },
      h3: {
        "typography-f-sf": true,
        "typography-w-400": true,
        "layout-m-0": true,
        "typography-sz-tl": true,
      },
      h4: {
        "typography-f-sf": true,
        "typography-w-400": true,
        "layout-m-0": true,
        "typography-sz-bl": true,
      },
      h5: {
        "typography-f-sf": true,
        "typography-w-400": true,
        "layout-m-0": true,
        "typography-sz-bm": true,
      },
      body: {},
      caption: {},
    },
    TextField: {
      container: {},
      label: {},
      element: {},
    },
    Video: {},
  },
  elements: {
    a: {},
    audio: {},
    body: {},
    button: {},
    h1: {},
    h2: {},
    h3: {},
    h4: {},
    h5: {},
    iframe: {},
    input: {},
    p: {},
    pre: {},
    textarea: {},
    video: {},
  },
  markdown: {
    p: [],
    h1: [],
    h2: [],
    h3: [],
    h4: [],
    h5: [],
    ul: [],
    ol: [],
    li: [],
    a: [],
    strong: [],
    em: [],
  },
};
