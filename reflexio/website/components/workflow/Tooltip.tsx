import type React from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
	children: React.ReactNode;
	isVisible: boolean;
	anchorRef: React.RefObject<HTMLDivElement | null>;
	borderColor: string;
	onMouseEnter?: () => void;
	onMouseLeave?: () => void;
}

export function Tooltip({
	children,
	isVisible,
	anchorRef,
	borderColor,
	onMouseEnter,
	onMouseLeave,
}: TooltipProps) {
	const tooltipRef = useRef<HTMLDivElement>(null);
	const [position, setPosition] = useState({
		top: 0,
		left: 0,
		placement: "bottom" as "bottom" | "top" | "left" | "right",
	});

	useEffect(() => {
		if (!isVisible || !anchorRef.current || !tooltipRef.current) return;

		const updatePosition = () => {
			const anchor = anchorRef.current?.getBoundingClientRect();
			const tooltip = tooltipRef.current?.getBoundingClientRect();

			if (!anchor || !tooltip) return;

			const viewportWidth = window.innerWidth;
			const viewportHeight = window.innerHeight;
			const scrollX = window.scrollX;
			const scrollY = window.scrollY;

			// Calculate available space in each direction
			const spaceAbove = anchor.top;
			const spaceBelow = viewportHeight - anchor.bottom;
			const spaceLeft = anchor.left;
			const spaceRight = viewportWidth - anchor.right;

			let top = 0;
			let left = 0;
			let placement: "bottom" | "top" | "left" | "right" = "bottom";

			// Determine best placement
			if (spaceBelow >= tooltip.height + 20 || spaceBelow >= spaceAbove) {
				// Place below
				placement = "bottom";
				top = anchor.bottom + scrollY + 10;
				left = anchor.left + scrollX + anchor.width / 2 - tooltip.width / 2;
			} else if (spaceAbove >= tooltip.height + 20) {
				// Place above
				placement = "top";
				top = anchor.top + scrollY - tooltip.height - 10;
				left = anchor.left + scrollX + anchor.width / 2 - tooltip.width / 2;
			} else if (spaceRight >= tooltip.width + 20) {
				// Place right
				placement = "right";
				top = anchor.top + scrollY + anchor.height / 2 - tooltip.height / 2;
				left = anchor.right + scrollX + 10;
			} else if (spaceLeft >= tooltip.width + 20) {
				// Place left
				placement = "left";
				top = anchor.top + scrollY + anchor.height / 2 - tooltip.height / 2;
				left = anchor.left + scrollX - tooltip.width - 10;
			} else {
				// Fallback: place below and adjust horizontally to fit
				placement = "bottom";
				top = anchor.bottom + scrollY + 10;
				left = anchor.left + scrollX + anchor.width / 2 - tooltip.width / 2;
			}

			// Ensure tooltip stays within viewport horizontally
			if (left < 10) {
				left = 10;
			} else if (left + tooltip.width > viewportWidth - 10) {
				left = viewportWidth - tooltip.width - 10;
			}

			// Ensure tooltip stays within viewport vertically
			if (top < 10) {
				top = 10;
			} else if (top + tooltip.height > viewportHeight + scrollY - 10) {
				top = viewportHeight + scrollY - tooltip.height - 10;
			}

			setPosition({ top, left, placement });
		};

		updatePosition();

		// Update on scroll or resize
		window.addEventListener("scroll", updatePosition, true);
		window.addEventListener("resize", updatePosition);

		return () => {
			window.removeEventListener("scroll", updatePosition, true);
			window.removeEventListener("resize", updatePosition);
		};
	}, [isVisible, anchorRef]);

	if (!isVisible) return null;

	const tooltipContent = (
		<div
			ref={tooltipRef}
			className="fixed p-5 bg-white rounded-xl shadow-2xl text-xs max-w-md border-2 transition-opacity duration-200"
			style={{
				top: position.top,
				left: position.left,
				borderColor: borderColor,
				maxHeight: "400px",
				overflowY: "auto",
				zIndex: 9999,
				pointerEvents: "auto",
			}}
			onMouseEnter={onMouseEnter}
			onMouseLeave={onMouseLeave}
		>
			{children}
		</div>
	);

	// Render in portal to avoid overflow issues
	return typeof window !== "undefined"
		? createPortal(tooltipContent, document.body)
		: null;
}
