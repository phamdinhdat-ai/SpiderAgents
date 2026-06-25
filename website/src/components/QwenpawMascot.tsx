/**
 * openspider mascot (same as logo symbol). Used in Hero and Nav.
 */
import { CatPawIcon } from "./CatPawIcon";

interface openspiderMascotProps {
  size?: number;
  className?: string;
}

export function openspiderMascot({
  size = 80,
  className = "",
}: openspiderMascotProps) {
  return <CatPawIcon size={size} className={className} />;
}
