"use client";

import { Menu as MenuPrimitive } from "@base-ui/react/menu";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const DropdownMenu = MenuPrimitive.Root;
export const DropdownMenuTrigger = MenuPrimitive.Trigger;

/** Portalled, positioned popup. Defaults to opening below and end-aligned with the
 * trigger; focus-trapped and Esc-dismissable by Base UI. */
export function DropdownMenuContent({
  className,
  sideOffset = 8,
  align = "end",
  ...props
}: ComponentProps<typeof MenuPrimitive.Popup> & {
  sideOffset?: number;
  align?: "start" | "center" | "end";
}) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner sideOffset={sideOffset} align={align} className="z-50">
        <MenuPrimitive.Popup
          className={cn(
            "min-w-40 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg",
            "transition-all duration-150 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0",
            className,
          )}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  );
}

const itemClass =
  "flex w-full cursor-default items-center gap-2 rounded-md px-2 py-2 text-sm outline-none select-none data-[highlighted]:bg-muted data-[highlighted]:text-foreground";

export function DropdownMenuItem({
  className,
  ...props
}: ComponentProps<typeof MenuPrimitive.Item>) {
  return <MenuPrimitive.Item className={cn(itemClass, className)} {...props} />;
}

/** A menu item that navigates — renders an `<a>` (pass `render={<Link .../>}` for
 * client-side routing). */
export function DropdownMenuLinkItem({
  className,
  ...props
}: ComponentProps<typeof MenuPrimitive.LinkItem>) {
  return <MenuPrimitive.LinkItem className={cn(itemClass, className)} {...props} />;
}
