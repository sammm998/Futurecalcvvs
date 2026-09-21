import { useTilt, tiltStyle } from "./tilt";

/* A plane that leans towards the reader.
 *
 * Used for the furniture of the signed-in side - a project, a drawing, a run - so a list reads as things lying
 * on a surface rather than as rules across a page. It is never used on the sheet itself: a drawing that moves
 * under the pointer is a drawing you cannot trace a run on.
 */
export default function Tilted({ as = "div", className = "", deg = 4, lift = 8, children, ...rest }: {
  as?: "div" | "article" | "li";
  className?: string;
  deg?: number;
  lift?: number;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  const { tilt, handlers } = useTilt(deg);
  const Tag = as as any;
  return (
    <div className="tiltwrap">
      <Tag className={`${className} tilt`} {...handlers} {...rest} style={tiltStyle(tilt, lift)}>
        {children}
      </Tag>
    </div>
  );
}
