import { displayNameFor, SPLIT_LABELS } from "../domain/classes";
import { formatPercent } from "../domain/format";
import { type ImageItem, thumbnailUrl } from "../domain/images";

export function ThumbnailCard({
  image,
  selected = false,
  focused = false,
  onToggle,
  onOpen,
}: {
  image: ImageItem;
  selected?: boolean;
  focused?: boolean;
  onToggle?: () => void;
  onOpen?: () => void;
}) {
  const labelText =
    image.label !== null ? displayNameFor(image.label.class_id) : null;
  const suggestionText =
    image.suggestion !== null
      ? displayNameFor(image.suggestion.class_id)
      : null;

  return (
    <article
      className={focused ? "thumb-card thumb-card--focused" : "thumb-card"}
      data-testid={`thumb-${image.ref}`}
      data-ref={image.ref}
    >
      {onToggle !== undefined ? (
        <label className="thumb-card__check">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={`${image.original_name} を選択`}
          />
        </label>
      ) : null}
      <button
        type="button"
        className="thumb-card__image"
        onClick={onOpen ?? onToggle}
      >
        <img
          src={thumbnailUrl(image.ref)}
          alt={image.original_name}
          width={image.width}
          height={image.height}
        />
      </button>
      <p className="thumb-card__name">{image.original_name}</p>
      <p className="thumb-card__meta">{SPLIT_LABELS[image.split]}</p>
      <p className="thumb-card__badges">
        {labelText !== null ? (
          <span className="badge badge--label">確定: {labelText}</span>
        ) : (
          <span className="badge badge--none">未ラベル</span>
        )}
        {suggestionText !== null && image.suggestion !== null ? (
          <span className="badge badge--suggestion">
            候補: {suggestionText} {formatPercent(image.suggestion.confidence)}
          </span>
        ) : null}
      </p>
    </article>
  );
}
