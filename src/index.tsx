import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaShieldAlt } from "react-icons/fa";
import { Content } from "./Content";

export default definePlugin(() => ({
  name: "VPN Deck AWG",
  titleView: <div className={staticClasses.Title}>VPN Deck AWG</div>,
  content: <Content />,
  icon: <FaShieldAlt />,
  onDismount() {},
}));
