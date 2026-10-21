import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

export function QuoteEditorMenu({ label, icon: Icon, children, testId }) {
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button type="button" variant="outline" className="quote-menu-trigger" data-testid={testId}>
        {Icon && <Icon size={16} aria-hidden="true" />}{label}<ChevronDown size={14} aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="quote-action-menu" sideOffset={8}>{children}</DropdownMenuContent>
  </DropdownMenu>;
}
