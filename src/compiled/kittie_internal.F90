module kittie_internal

#	ifdef USE_MPI
		use mpi
#	endif

	use adios2

	implicit none


#	ifdef USE_MPI
		logical :: use_mpi=.true.
#	else
		logical :: use_mpi=.false.
#	endif

	character(len=8), parameter :: writing=".writing"
	character(len=8), parameter :: reading=".reading"
	integer :: iounit=20

	! This is the namespace all the Kittie ADIOS-2 I/O lives in. Nicely, this will be completely independent of anything else ADIOS-2.
	type(adios2_adios) :: kittie_adios


	contains

		function string_copy(thing) result(new)
			character(len=*), intent(in) :: thing
			character(len=:), allocatable :: new
			allocate(character(len_trim(thing)) :: new)
			new = thing
		end function string_copy


		function capitalize(strIn) result(strOut)
			character(len=*), intent(in) :: strIn
			character(len=:), allocatable :: strOut
			integer :: i,j

			strOut = string_copy(strIn)
			do i = 1, len(strOut)
				j = iachar(strIn(i:i))
				if (j>= iachar("a") .and. j<=iachar("z") ) then
					strOut(i:i) = achar(iachar(strIn(i:i))-32)
				else
					strOut(i:i) = strIn(i:i)
				end if
			end do
		end function capitalize


		subroutine delete_existing(fname)
			character(len=*), intent(in) :: fname
			integer :: stat
			open(unit=iounit, iostat=stat, file=fname, status='old')
			close(iounit, status="delete")
		end subroutine delete_existing


		subroutine touch_file(fname)
			character(len=*), intent(in) :: fname
			open(unit=iounit, file=fname, status='new')
			close(iounit)
		end subroutine touch_file

end module kittie_internal
